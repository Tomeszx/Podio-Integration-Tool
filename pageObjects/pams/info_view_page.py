import contextlib
import traceback

from result import Ok, Err, Result, is_err
from selenium.webdriver.chrome.webdriver import WebDriver

from apiObjects.google_sheet_api import upload_file
from pageObjects.base_methods import Locator, BaseMethods

MARKETS_NAMES = {
    "NL": "Netherlands", "DK": "Denmark", "SE": "Sweden", "BE": "Belgium", "FR": "France", "IT": "Italy", "ES": "Spain",
    "DE": "Germany", "PL": "Poland", "UK": "United Kingdom", "FI": "Finland", "CN": "China", "NO": "Norway"
}


class InfoViewPage(BaseMethods):
    core_market_text = Locator(arg='//*[@data-name="preview-primary-core-platform"]')
    market_id_text = Locator(arg='//*[@data-name="shop-id-{}"]')
    location_name_input = Locator(arg='//input[@name="name"]')
    core_market_dropdown = Locator(arg='//div[@data-name="partner-core-market"]')
    local_currency_dropdown = Locator(arg='//div[@data-name="localCurrency"]')
    source_language_dropdown = Locator(arg='//div[@data-name="sourceLanguage"]')
    save_and_next_button = Locator(arg='//button[@data-name="button-save-and-next"]')

    def __init__(self, driver: WebDriver, data: dict, market: str):
        super().__init__(driver)
        self.data = data
        self.market = market

    def _get_ids(self, expected_ids: list) -> Result[list, list]:
        new_ids = []
        for shop_id in expected_ids:
            market = shop_id.split("-")[0]
            new_id = self.get_elements(self.market_id_text.__format__(market.replace('UK', 'GB')))
            if new_id and new_id[0].text.isdigit():
                new_ids.append(f"{market}-{new_id[0].text}")

        if len(new_ids) < len(expected_ids):
            return Err(new_ids)
        return Ok(new_ids)

    def add_location_info_and_go_to_next_step(self) -> Result[None, str]:
        try:
            self.wait_for_clickability(self.location_name_input, 15)

            self.write(self.location_name_input, self.data['partner_name'])
            self.select(self.core_market_dropdown, MARKETS_NAMES[self.market])
            self.select(self.local_currency_dropdown, 'EUR')
            self.select(self.source_language_dropdown, 'English')
            self.click(self.save_and_next_button)

            self.wait_for_invisibility(self.location_name_input, 10)
        except Exception as e:
            print(e)
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating location info. '
                f'Screenshot: {screen_url} \nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def wait_for_ids(self, expected_ids: list) -> Result[tuple[None, list], tuple[str, list]]:
        self.open(f'/preview/{self.data["pams_partner_id"]}/info')
        self.wait_for_visibility(self.core_market_text, 15)

        core_market = self.get_attribute(self.core_market_text, 'innerText')
        core_market_dict_index = list(MARKETS_NAMES.values()).index(core_market)

        with contextlib.suppress(Exception):
            self.wait_for_visibility(self.market_id_text.__format__(
                list(MARKETS_NAMES)[core_market_dict_index]), 30
            )

        screen_url = upload_file(self.make_screen(f'{self.market} - waiting for ids'))
        error_comment = f"Couldn't map all created ids in PaMS.\nScreenshot: {screen_url}"
        core_id = self.get_elements(self.market_id_text.__format__(list(MARKETS_NAMES)[core_market_dict_index]))
        if not core_id or not core_id[0].text.isdigit():
            return Err((error_comment, []))

        result = self._get_ids(expected_ids)
        if is_err(result):
            return Err((error_comment, result.err_value))
        return Ok((None, result.ok_value))
