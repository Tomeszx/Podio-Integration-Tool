from __future__ import annotations
import logging

from io import BytesIO
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait


logging.getLogger("httpx").setLevel(logging.ERROR)


class Locator:
    def __init__(self, locator_type: By = By.XPATH, arg: str = None):
        self.value: tuple = locator_type, arg

    def __format__(self, format_spec):
        return Locator(self.value[0], arg=self.value[1].format(format_spec))

    def __iter__(self) -> tuple[By, str]:
        yield from self.value

    def __getitem__(self, item):
        return self.value[item]


class BaseMethods:

    def __init__(self, driver: WebDriver):
        self.driver = driver

    def open(self, desired_path: str) -> str:
        base_url = 'https://proxy-partner-management-service-uat.miinto.net/partners'
        self.driver.get(f'{base_url}{desired_path}')

        return base_url

    def get_element(self, locator: Locator) -> WebElement:
        return self.driver.find_element(*locator)

    def get_elements(self, locator: Locator) -> [WebElement]:
        return self.driver.find_elements(*locator)

    def get_attribute(self, locator: Locator, attribute_name: str) -> str:
        return self.get_element(locator).get_attribute(attribute_name)

    def click(self, locator: Locator) -> Locator:
        self.get_element(locator).click()
        return locator

    def check(self, locator: Locator, is_checked: bool) -> Locator:
        if self.get_attribute(locator, 'aria-checked') != f'{is_checked}'.lower():
            self.click(locator)
        return locator

    def select(self, locator: Locator, option: str) -> None:
        self.click(locator)
        self.wait_for_clickability(Locator(arg=f'.//span/span[text()="{option}"]'), 5).click()

    def write(self, locator: Locator, value: str) -> None:
        element = self.driver.find_element(*locator)
        element.clear()
        element.send_keys(value)

    def clear_input(self, locator: Locator) -> None:
        self.driver.find_element(*locator).clear()

    def wait_for(self, conditions=None, timeout=15, only_readystate=False) -> WebElement:
        wait = WebDriverWait(self.driver, timeout)
        wait.until(lambda driver: driver.execute_script('return document.readyState') == 'complete')
        if self.driver.execute_script('return document.readyState') != 'complete':
            wait.until(lambda driver: driver.execute_script('return document.readyState') == 'complete')
        if not only_readystate:
            return wait.until(conditions)

    def wait_for_visibility(self, locator: Locator, timeout=15) -> Locator:
        self.wait_for(EC.visibility_of_element_located(locator.value), timeout)
        return locator

    def wait_for_clickability(self, locator: Locator, timeout=15) -> WebElement:
        return self.wait_for(EC.element_to_be_clickable(locator.value), timeout)

    def wait_for_invisibility(self, locator: Locator, timeout=15) -> Locator:
        WebDriverWait(self.driver, timeout).until_not(EC.visibility_of_element_located(locator.value))
        return locator

    def make_screen(self, title: str) -> BytesIO:
        origin_size = self.driver.get_window_size()
        full_height = int(self.driver.execute_script("return document.body.scrollHeight"))

        if full_height > origin_size['height']:
            self.driver.set_window_size(1920, full_height)
        screen = BytesIO(self.driver.get_screenshot_as_png())
        screen.name = title

        self.driver.set_window_size(origin_size['width'], origin_size['height'])

        return screen
