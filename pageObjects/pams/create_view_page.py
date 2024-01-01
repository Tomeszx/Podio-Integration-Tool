import traceback

from result import Ok, Err, Result
from selenium.webdriver.chrome.webdriver import WebDriver

from apiObjects.google_sheet_api import upload_file
from pageObjects.base_methods import Locator
from pageObjects.pams.edit_view_page import EditViewPage


class CreateViewPage(EditViewPage):
    username_input = Locator(arg='//input[@name="username"]')
    password_input = Locator(arg='//input[@name="password"]')
    password_repeat_input = Locator(arg='//input[@name="passwordRepeat"]')
    save_and_next_button = Locator(arg='//button[@data-name="button-save-and-next"]')
    finish_button = Locator(arg='//button[@data-name="button-finish"]')
    add_market_button = Locator(arg='//button[@data-name="button-create-market"]')

    def __init__(self, driver: WebDriver, podio_data: dict, market: str):
        super().__init__(driver, podio_data, market)

    def add_password_and_username(self) -> Result[None, str]:
        try:
            self.wait_for_clickability(self.username_input, 15)
            self.write(self.password_input, self.podio_data['Password'])
            self.write(self.password_repeat_input, self.podio_data['Password'])
            self.write(self.username_input, self.podio_data['Order_Email'])
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating Shop Name or Legal Name. '
                f'Screenshot: {screen_url} \nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_all_fields_in_create_view(self) -> list[Result]:
        try:
            self.wait_for_clickability(self.vat_zone_dropdown, 15)
            results = [
                self.add_password_and_username(),
                *self.update_all_fields_in_edit_view()
            ]
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return [Err(
                f'Issue while creating new market. '
                f'Screenshot: {screen_url} \nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )]
        return results

    def save_create_view(self, values_before_changes: dict) -> Result[dict, str]:
        if self.get_elements(self.finish_button):
            return self.save(values_before_changes, custom_button=self.finish_button)
        return self.save(values_before_changes)
