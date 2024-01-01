import os
import pycountry
import pandas as pd
import traceback

from apiObjects.google_sheet_api import upload_file
from pageObjects.base_methods import BaseMethods, Locator
from phonenumbers import format_number, parse, PhoneNumberFormat
from result import Ok, Err, Result, is_err
from selenium.webdriver.chrome.webdriver import WebDriver
from schwifty import IBAN, bic


BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('/objects/pageObjects', '')


class EditViewPage(BaseMethods):
    market_selector = Locator(arg="//button[@role='tab']/span[text()='{}']")
    user_type_dropdown = Locator(arg='//div[@data-name="userType"]')
    activity_dropdown = Locator(arg='//div[@data-name="activity"]')
    shop_name_input = Locator(arg='//input[@name="shopName"]')
    legal_name_input = Locator(arg='//input[@name="legalName"]')
    order_email_input = Locator(arg='//input[@name="orderEmail"]')
    payment_method_dropdown = Locator(arg='//div[@data-name="paymentMethod"]')
    bank_account_number_input = Locator(arg='//input[@name="bankAccountNumber"]')
    bank_code_input = Locator(arg='//input[@name="bankRegistrationNumber"]')
    vat_tax_input = Locator(arg='//input[@name="CVR"]')
    shipping_name_input = Locator(arg='//input[@name="shippingAddresses.{}.name"]')
    shipping_street_1_input = Locator(arg='//input[@name="shippingAddresses.{}.street1"]')
    shipping_street_2_input = Locator(arg='//input[@name="shippingAddresses.{}.street2"]')
    shipping_zip_code_input = Locator(arg='//input[@name="shippingAddresses.{}.zipCode"]')
    shipping_city_input = Locator(arg='//input[@name="shippingAddresses.{}.city"]')
    shipping_country_dropdown = Locator(arg='//div[@data-name="shippingAddresses.{}.country"]')
    shipping_tab_buttons = Locator(arg='//button[contains(@data-name, "button-shipping-address-")]')
    shipping_tab_button = Locator(arg='//button[@data-name="button-shipping-address-{}"]')
    shipping_remove_button = Locator(arg='//button[@data-name="button-remove-shipping-address"]')
    shipping_add_button = Locator(arg='//button[@data-name="button-add-shipping-address"]')
    contacts_0_email_input = Locator(arg='//input[@name="contacts.0.email"]')
    contacts_0_name_input = Locator(arg='//input[@name="contacts.0.name"]')
    contacts_1_email_input = Locator(arg='//input[@name="contacts.1.email"]')
    contacts_1_name_input = Locator(arg='//input[@name="contacts.1.name"]')
    contacts_phone_number_input = Locator(arg='//input[@name="phoneNumber"]')
    invoicing_country_dropdown = Locator(arg='//div[@data-name="invoicingAddress.country"]')
    invoicing_street_1_input = Locator(arg='//input[@name="invoicingAddress.street1"]')
    invoicing_street_2_input = Locator(arg='//input[@name="invoicingAddress.street2"]')
    invoicing_zip_code_input = Locator(arg='//input[@name="invoicingAddress.zipCode"]')
    invoicing_city_input = Locator(arg='//input[@name="invoicingAddress.city"]')
    invoicing_emails_input = Locator(arg='//input[@name="invoicingEmails"]')
    signup_date_input = Locator(arg='//input[@name="signupDate"]')
    signed_by_input = Locator(arg='//input[@name="signedBy"]')
    consultant_input = Locator(arg='//input[@name="consultant"]')
    customer_care_input = Locator(arg='//input[@name="customerCare"]')
    transfer_price_restriction_input = Locator(arg='//input[@name="transferPriceRestriction"]')
    order_distribution_delay_input = Locator(arg='//input[@name="orderDistributionDelay"]')
    return_name_input = Locator(arg='//input[@name="returnAddress.name"]')
    return_street_1_input = Locator(arg='//input[@name="returnAddress.street1"]')
    return_street_2_input = Locator(arg='//input[@name="returnAddress.street2"]')
    return_zip_code_input = Locator(arg='//input[@name="returnAddress.zipCode"]')
    return_city_input = Locator(arg='//input[@name="returnAddress.city"]')
    return_country_dropdown = Locator(arg='//div[@data-name="returnAddress.country"]')
    return_copy_from_shipping_button = Locator(arg='//button[@data-name="button-copy-first-shipping-address"]')
    subscription_type_dropdown = Locator(arg='//div[@data-name="subscriptionType"]')
    reducer_type_dropdown = Locator(arg='//div[@data-name="reducerType"]')
    display_tick_box = Locator(arg='//input[@data-name="featureDisplayMiintoAddress"]/..//button')
    shipping_service_tick_box = Locator(arg='//input[@data-name="featureMiintoShippingService"]/..//button')
    free_shipping_service_tick_box = Locator(arg='//input[@data-name="featureFreeMiintoShippingService"]/..//button')
    price_restriction_tick_box = Locator(arg='//input[@data-name="featureTransferPriceRestriction"]/..//button')
    distribution_delay_tick_box = Locator(arg='//input[@data-name="featureOrderDistributionDelay"]/..//button')
    vat_zone_dropdown = Locator(arg='//div[@data-name="vatZone"]')
    vat_zone_disabled = Locator(arg='//div[@data-name="vatZone"]/button[@disabled]')
    save_button = Locator(arg='//button[@data-name="button-on-save-edit-form"]')
    edit_market_button = Locator(arg='//button[@data-name="button-market-or-partner-edit"]')
    preview_mode = Locator(arg='//div[@data-component="partner-preview"]')
    edit_view_mode = Locator(arg='//div[@data-component="partner-edit"]')

    def __init__(self, driver: WebDriver, podio_data: dict, market: str):
        super().__init__(driver)
        self.podio_data = podio_data
        self.market = market

    @staticmethod
    def _get_street(street: str) -> tuple:
        street_1, street_2 = "", ""
        for word in street.replace("\n", " ").split(" "):
            if len(f"{street_1} {word}") <= 30:
                street_1 += f" {word}"
            elif len(f"{street_2} {word}") <= 30:
                street_2 += f" {word}"
        return street_1, street_2

    def _get_bank_account_number(self) -> Result[tuple, str]:
        field_name_podio = 'Bank_Account_Number_-_IBAN_(format:_PL123456789)'
        try:
            return Ok((IBAN(self.podio_data[field_name_podio]).compact, "IBAN/SWIFT"))
        except Exception as e:
            if self.podio_data[field_name_podio].count(";") == 0:
                msg = f'Can not find separator ";".\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
                return Err(msg)
        try:
            for account in self.podio_data[field_name_podio].replace(" ", "").replace("\n", "").split(";"):
                if self.market in account.split('IBAN:')[0].split(',') and 'IBAN:' in account:
                    iban_number = account.split("IBAN:")[1]
                    return Ok((IBAN(iban_number).compact, "IBAN/SWIFT"))
                elif self.market in account.split('Account:')[0].split(',') and 'Account:' in account:
                    account_number = account.split("Account:")[1]
                    return Ok((account_number, "Bank transfer"))
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating {field_name_podio}. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Err(f'The Iban is not correct. Please check if {self.market} is not missing or if the number is correct')

    def _get_bank_code(self) -> Result[str, str]:
        field_name_podio = 'Bank_Account_Number_-_SWIFT'
        try:
            return Ok(bic.BIC(self.podio_data[field_name_podio]).compact)
        except Exception as e:
            if self.podio_data[field_name_podio].count(";") == 0:
                return Err(f'Can not find separator ";".\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}')
        try:
            for account in self.podio_data[field_name_podio].replace(" ", "").replace("\n", "").split(";"):
                if self.market in account.split('SWIFT:')[0].split(',') and 'SWIFT:' in account:
                    bank_code = account.split("SWIFT:")[1]
                    return Ok(bic.BIC(bank_code).compact)
                elif f"{self.market}CODE:" in account:
                    account_number = account.split("CODE:")[1]
                    return Ok(account_number)
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating {field_name_podio}. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Err(f'Issue while updating {field_name_podio} on {self.market} market.')

    def _get_phone_number(self, phone_number: str) -> str:
        try:
            return format_number(parse(phone_number), PhoneNumberFormat.E164)
        except Exception:
            return format_number(parse(phone_number, self.podio_data['Home_Market']), PhoneNumberFormat.E164)

    def _parse_shipping_locations(self, shipping_field_name: str) -> Result[list, str]:
        try:
            data = []
            for address in self.podio_data[shipping_field_name].replace("\n", "").split(";"):
                if address.replace(" ", "") == "":
                    continue
                country_code = address.split('CountryCode=')[1].split('|')[0]
                data.append({
                    'Shipping_Address_-_Country': pycountry.countries.get(alpha_2=country_code).name,
                    'Shipping_Address_-_City': address.split('City=')[1].split('|')[0],
                    'Shipping_Address_-_Street': address.split('Street=')[1].split('|')[0],
                    'partner_name': address.split('Name=')[1].split('|')[0],
                    'Shipping_Address_-_Zip_code': address.split('Zipcode=')[1].split('|')[0]
                })
            return Ok(data)
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Some field is missing in additional shipping. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )

    def _delete_all_additional_shipping_locations(self) -> Result[None, str]:
        try:
            for _ in self.get_elements(self.shipping_tab_buttons)[1:]:
                last_tab_index = len(self.get_elements(self.shipping_tab_buttons)) - 1

                self.click(self.shipping_tab_button.__format__(str(last_tab_index)))
                self.click(self.shipping_remove_button)
                self.wait_for_invisibility(self.shipping_tab_button.__format__(str(last_tab_index)), 5)
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while deleting old shipping locations. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def _get_shipping_fields_locators(self) -> dict:
        return {
            'shipping_name_input': self.shipping_name_input,
            'shipping_street_1_input': self.shipping_street_1_input,
            'shipping_street_2_input': self.shipping_street_2_input,
            'shipping_city_input': self.shipping_city_input,
            'shipping_zip_code_input': self.shipping_zip_code_input,
            'shipping_country_dropdown': Locator(
                self.shipping_country_dropdown[0], f'{self.shipping_country_dropdown[1]}/button/span'
            )
        }

    def _get_shipping_values(self) -> dict:
        data = {}
        for i, button in enumerate(self.get_elements(self.shipping_tab_buttons)):
            for name, locator in self._get_shipping_fields_locators().items():
                button.click()
                self.wait_for_visibility(locator.__format__(str(i)))
                if 'input' in name:
                    data[f'{name} ~tab-{i}'] = self.get_attribute(locator.__format__(str(i)), 'value')
                else:
                    data[f'{name} ~tab-{i}'] = self.get_attribute(locator.__format__(str(i)), 'innerText')
        return data

    def update_name_section(self) -> Result[None, str]:
        try:
            self.write(self.shop_name_input, self.podio_data['partner_name'])
            self.write(self.legal_name_input, self.podio_data['Legal_Name'])
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating Shop Name or Legal Name. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_order_email(self) -> Result[None, str]:
        if len(self.podio_data['Order_Email']) > 1:
            return Err("The Order Email could be the only one in Podio.")
        try:
            self.write(self.order_email_input, self.podio_data['Order_Email'])
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(f'Issue while updating Order Email. '
                       f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}')
        return Ok(None)

    def update_vat_tax_number(self) -> Result[None, str]:
        try:
            self.write(self.vat_tax_input, self.podio_data['VAT_TAX_Number'])
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating VAT TAX Number. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_price_restriction(self) -> Result[None, str]:
        try:
            self.check(self.price_restriction_tick_box, True)
            self.wait_for_clickability(self.transfer_price_restriction_input, 3)
            self.write(self.transfer_price_restriction_input, self.podio_data.get('Transfer_price_restriction_%', '50'))
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating price restriction. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_order_distribution_delay(self) -> Result[None, str]:
        try:
            is_checked = len(self.podio_data.get('Order_distribution_delay_(min)', '')) > 0
            self.check(self.distribution_delay_tick_box, is_checked)
            if is_checked:
                self.wait_for_clickability(self.order_distribution_delay_input, 3)
                self.write(self.order_distribution_delay_input, self.podio_data.get('Order_distribution_delay_(min)', ''))
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating order distribution delay. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_date_of_signing(self) -> Result[None, str]:
        try:
            full_date = str(self.podio_data["Date_of_signing"][0].date())
            for date_part in reversed(full_date.split("-")):
                self.write(self.signup_date_input, date_part)
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating date of signing. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_status(self) -> Result[None, str]:
        try:
            if "offline" in self.podio_data['Status_on_Admin'] or "Temp Closed" in self.podio_data['Status_on_Admin']:
                self.select(self.activity_dropdown, "Temp. Closed")
            elif "Churn Closed" in self.podio_data['Status_on_Admin']:
                self.select(self.activity_dropdown, "Closed")
            elif "Active" in self.podio_data['Status_on_Admin'] or "online" in self.podio_data['Status_on_Admin']:
                self.select(self.activity_dropdown, "Miinto Full")
            else:
                return Err(f'Missing status option for {self.podio_data["Status_on_Admin"]}.')
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(f'Issue while updating status. '
                       f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}')
        return Ok(None)

    def update_vat_zone(self) -> Result[None | str, str]:
        try:
            self.wait_for_clickability(self.vat_zone_dropdown, 15)
            if self.get_elements(self.vat_zone_disabled):
                return Ok('The vat zone dropdown is disabled. There is no need to update this field.')

            with open(f"{BASE_PATH}/additional_files/vat_zones.csv", "r") as file:
                vat_zones = pd.read_csv(file, index_col=0)
                vat_zone_dict = vat_zones.get(self.podio_data['Home_Market'], {})
                vat_zone_value = vat_zone_dict.get(self.market, 'EU')
                self.select(self.vat_zone_dropdown, vat_zone_value)
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(f'Issue while updating vat zone. '
                       f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}')
        return Ok(None)

    def update_shipping_agreement_section(self) -> Result[None, str]:
        try:
            if "FREE" in self.podio_data['Miinto_Shipping_Agreement']:
                self.check(self.shipping_service_tick_box, True)
                self.check(self.free_shipping_service_tick_box, True)
            elif self.podio_data['Miinto_Shipping_Agreement'] == "Yes":
                self.check(self.shipping_service_tick_box, True)
                self.check(self.free_shipping_service_tick_box, False)
            else:
                self.check(self.shipping_service_tick_box, False)
                self.check(self.free_shipping_service_tick_box, False)
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating Shipping Agreement. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_bank_account_section(self) -> Result[None, str]:
        bank_account = self._get_bank_account_number()
        if is_err(bank_account):
            return bank_account
        bank_code = self._get_bank_code()
        if is_err(bank_account):
            return bank_account

        try:
            self.select(self.payment_method_dropdown, bank_account.ok_value[1])
            self.wait_for_clickability(self.bank_account_number_input)
            self.write(self.bank_account_number_input, bank_account.ok_value[0])
            self.write(self.bank_code_input, bank_code.ok_value)
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating bank account section. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_shipping_section(self, index: int, data: dict, s_type='shipping') -> Result[None, str]:
        my_object = EditViewPage.__dict__
        try:
            if self.get_elements(self.shipping_tab_buttons):
                self.click(self.shipping_tab_button.__format__(str(index)))

            self.select(my_object[f'{s_type}_country_dropdown'].__format__(index), data['Shipping_Address_-_Country'])
            self.write(my_object[f'{s_type}_name_input'].__format__(index), data['partner_name'])
            self.write(my_object[f'{s_type}_city_input'].__format__(index), data['Shipping_Address_-_City'])
            self.write(my_object[f'{s_type}_zip_code_input'].__format__(index), data['Shipping_Address_-_Zip_code'])
            street = self._get_street(data['Shipping_Address_-_Street'])
            self.write(my_object[f'{s_type}_street_1_input'].__format__(index), street[0])
            self.write(my_object[f'{s_type}_street_2_input'].__format__(index), street[1])
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating {s_type}_section. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)
    
    def update_invoicing_section(self) -> Result[None, str]:
        try:
            self.select(self.invoicing_country_dropdown, self.podio_data['Invoicing_Address_-_Country'])
            self.write(self.invoicing_zip_code_input, self.podio_data['Invoicing_Address_-_Zipcode'])
            self.write(self.invoicing_city_input, self.podio_data['Invoicing_Address_-_City'])
            self.write(self.invoicing_emails_input, ";".join(self.podio_data['Invoicing_Emails']))
            street = self._get_street(self.podio_data['Invoicing_Address_-_Street'])
            self.write(self.invoicing_street_1_input, street[0])
            self.write(self.invoicing_street_2_input, street[1])
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating invoicing section. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_contact_person_section(self) -> Result[None, str]:
        try:
            self.write(self.contacts_0_name_input, self.podio_data['Contact_person_1_-_name_&_surname'])
            self.write(self.contacts_0_email_input, self.podio_data['Contact_person_-_emails'][0])
            shop_phone_number = self.podio_data['Shop_phone_number_-_shipping_labels_and_customer_service']
            converted_number = self._get_phone_number(shop_phone_number)
            self.write(self.contacts_phone_number_input, converted_number)
            if len(self.podio_data['Contact_person_-_emails']) > 1:
                contact_person_2 = 'Contact_person_2_-_name_&_surname', self.podio_data['Contact_person_1_-_name_&_surname']
                self.write(self.contacts_1_name_input, self.podio_data.get(*contact_person_2))
                self.write(self.contacts_1_email_input, self.podio_data['Contact_person_-_emails'])
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating contact person section. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def add_additional_shipping_locations(self) -> Result[None, str]:
        result = self._delete_all_additional_shipping_locations()
        if is_err(result):
            return result

        try:
            locations = self._parse_shipping_locations('Additional_shipping_locations_-_Sender')
            if is_err(locations):
                return locations

            for index, location in enumerate(locations.ok_value, 1):
                self.click(self.shipping_add_button)
                update_result = self.update_shipping_section(index, location)
                if is_err(update_result):
                    return update_result
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating shipping locations section. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def add_return_shipping_locations(self, copy_from_shipping_if_none=False) -> Result[None, str]:
        try:
            if not self.podio_data.get('Return_address') and copy_from_shipping_if_none:
                self.wait_for_clickability(self.return_copy_from_shipping_button).click()
                return Ok(None)

            locations = self._parse_shipping_locations('Return_address')
            if is_err(locations):
                return locations

            update_result = self.update_shipping_section(0, locations.ok_value[0], 'return')
            if is_err(update_result):
                return update_result
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating return address. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_other_fields(self) -> Result[None, str]:
        try:
            shop_type = 'Brand' if self.podio_data['partner_type'] == 'Brands' else 'Shop'
            self.select(self.user_type_dropdown, shop_type)
            self.write(self.signed_by_input, self.podio_data['Signed_by'][0]['name'])
            self.write(self.consultant_input, self.podio_data['Signed_by'][0]['name'])
            self.write(self.customer_care_input, self.podio_data['Onboard_Responsible'][0]['name'])
            self.select(self.subscription_type_dropdown, 'Standard')
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating other fields. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_contact_and_invoicing(self):
        return [
            self.update_contact_person_section(),
            self.update_invoicing_section()
        ]

    def update_reducer_type(self, reducer_type: str) -> Result[None, str]:
        try:
            self.select(self.reducer_type_dropdown, reducer_type)
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while updating reducer type. '
                f'Screenshot: {screen_url}\nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(None)

    def update_all_fields_in_edit_view(self) -> list[Result]:
        results = [
            self.update_status(),
            self.update_vat_zone(),
            self.update_order_email(),
            self.update_other_fields(),
            self.update_name_section(),
            self.update_vat_tax_number(),
            self.update_date_of_signing(),
            self.update_invoicing_section(),
            self.update_price_restriction(),
            self.update_bank_account_section(),
            self.update_contact_person_section(),
            self.update_order_distribution_delay(),
            self.update_shipping_agreement_section(),
            self.update_shipping_section(0, self.podio_data),
            self.add_return_shipping_locations(copy_from_shipping_if_none=True)
        ]
        if 'Additional_shipping_locations_-_Sender' in self.podio_data:
            results.extend((
                self.add_additional_shipping_locations(),
            ))
        return results

    def get_all_values(self, url: str) -> dict:
        self.driver.get(url)
        self.wait_for_clickability(self.shop_name_input, 15)

        data = {}
        locators = filter(lambda locator: isinstance(locator[1], Locator), EditViewPage.__dict__.items())
        for name, locator in locators:
            if 'shipping' in name and 'button' not in name and 'tick_box' not in name:
                continue
            elif 'input' in name:
                data[name] = self.get_attribute(locator, 'value')
            elif 'dropdown' in name:
                locator = Locator(locator[0], f'{locator[1]}/button/span')
                data[name] = self.get_attribute(locator, 'innerText')
            elif 'tick_box' in name:
                data[name] = self.get_attribute(locator, 'aria-checked')
        data |= self._get_shipping_values()
        return data

    def save(self, values_before: dict, custom_button=None) -> Result[str, str]:
        try:
            current_url = self.driver.current_url
            self.wait_for_clickability(custom_button or self.save_button, 5).click()
            self.wait_for_visibility(self.preview_mode, 15)

            data = self.get_all_values(current_url)
            changes = ""
            for field_name, current_value in data.items():
                if values_before.get(field_name) != current_value:
                    changes += f"\n\n{field_name}:\n---\n\n >[{values_before.get(field_name, '')}]-->[{current_value}]"
        except Exception as e:
            screen_url = upload_file(self.make_screen(f'{self.market} - {e.__str__()}'))
            return Err(
                f'Issue while saving data in PaMS. '
                f'Screenshot: {screen_url} \nPython error: {traceback.format_exc().split("Stacktrace:")[0]}'
            )
        return Ok(changes)
