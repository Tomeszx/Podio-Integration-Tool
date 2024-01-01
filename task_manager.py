#!venv/bin/python3.9
import re

from apiObjects.podio_api import Podio
from pageObjects.pams.create_view_page import CreateViewPage
from pageObjects.pams.edit_view_page import EditViewPage
from pageObjects.pams.login_page import LoginPage
from pageObjects.pams.page_manager import PageManager
from result import is_err
from selenium.webdriver.chrome.webdriver import WebDriver


class Task:
    additional_shipping_locations = EditViewPage.add_additional_shipping_locations
    miinto_shipping_agreement = EditViewPage.update_shipping_agreement_section
    distribution_delay = EditViewPage.update_order_distribution_delay
    shop_phone_number = EditViewPage.update_contact_person_section
    create_core = CreateViewPage.update_all_fields_in_create_view
    other_markets = EditViewPage.update_all_fields_in_edit_view
    return_address = EditViewPage.add_return_shipping_locations
    invoicing_email = EditViewPage.update_contact_and_invoicing
    contact_person = EditViewPage.update_contact_person_section
    address_email = EditViewPage.update_contact_and_invoicing
    price_restriction = EditViewPage.update_price_restriction
    all_fields = EditViewPage.update_all_fields_in_edit_view
    name_field_change = EditViewPage.update_name_section
    iban = EditViewPage.update_bank_account_section
    order_email = EditViewPage.update_order_email
    status_on_admin = EditViewPage.update_status
    vat_tax = EditViewPage.update_vat_zone

    def __init__(self, title: str, all_shop_ids: str):
        self.title = re.sub('[/\s]', '_', title).lower()
        self.function = self._get_correct_function(all_shop_ids)

    def _get_correct_function(self, all_shop_ids: str):
        if self.title == 'Create core' and len(all_shop_ids) > 5:
            return EditViewPage.update_all_fields_in_edit_view
        return Task.__dict__[self.title]


class TasksManager:
    def __init__(self, comment_frequency: int, tokens: list, user_inputs: dict, chrome_options, driver: WebDriver):
        self.driver = driver
        self.comment_frequency = comment_frequency
        self.tokens = tokens
        self.user_inputs = user_inputs
        self.chrome_options = chrome_options
        self.podio_data = {}
        self.task = {}

    def _initialize_variables(self) -> None:
        self.podio = Podio(self.tokens, self.user_inputs)
        self.pams_manager = PageManager(self.driver, self.user_inputs, self.podio)

    def _manage_tasks(self, task_details: dict, data: dict) -> None:
        task = Task(task_details['part_title'], data.get('All_Shop_IDs', ''))
        result = self.pams_manager.run(task.function, data, task_details)

        if is_err(result):
            print(self.podio.add_error_comment(result.err_value, task_details, data, self.comment_frequency))
        else:
            self.podio.complete_task(task_details['task_id'])
            print(self.podio.add_comment(result.ok_value, task_details))

    def perform_data(self, tasks_array: list, tasks_fields: dict) -> None:
        LoginPage(self.driver, self.user_inputs).login()
        for i, task_row in enumerate(tasks_array[::-1], 1):
            print(f"\n{'':^60}[{i}/{len(tasks_array)}] {task_row['partner_name']} {task_row['task_text']}")

            self._initialize_variables()

            data = self.podio.get_partner_details(task_row['shop_item_id'])
            result = self.podio.prepare_data(data, task_row, tasks_fields)
            if is_err(result):
                print(self.podio.add_error_comment(result.err_value, task_row, data, self.comment_frequency))
                continue

            self._manage_tasks(task_row, data)
