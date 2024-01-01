from pageObjects.base_methods import BaseMethods, Locator
from selenium.webdriver.chrome.webdriver import WebDriver


class LoginPage(BaseMethods):
    username_input = Locator(arg='//*[@name="username"]')
    password_input = Locator(arg='//*[@name="password"]')
    login_button = Locator(arg='//button[@data-name="button-login-form"]')

    def __init__(self, driver: WebDriver, credentials: dict):
        super().__init__(driver)
        self.credentials = credentials

    def login(self) -> None:
        self.open('')
        self.wait_for_clickability(LoginPage.password_input)
        self.write(self.username_input, self.credentials['username_pams'])
        self.write(self.password_input, self.credentials['password_pams'])
        self.wait_for_clickability(self.login_button).click()
        self.wait_for_invisibility(self.password_input)
