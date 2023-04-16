import json
import time
import contextlib

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException

select_fields_names = json.load(open("Podio & PaMS fields/select_fields_names.json"))
input_fields_names = json.load(open("Podio & PaMS fields/input_fields_names.json"))
tickbox_class_names = json.load(open("Podio & PaMS fields/tickbox_class_names.json"))
vat_zones = pd.read_csv('Vat Zones/vat_zones.csv', index_col=0)
markets = {"NL": "Netherlands", "DK": "Denmark", "SE": "Sweden", "BE": "Belgium", "FR": "France",
           "IT": "Italy", "ES": "Spain", "DE": "Germany", "PL": "Poland", "UK": "United Kingdom",
           "FI": "Finland", "CN": "China", "NO": "Norway"}


class PaMS:
    def __init__(self, credentials: dict):
        self.credentials = credentials

    def login(self, website):
        website.find_element(By.XPATH, '//*[@name="username"]').send_keys(self.credentials['username_pams'])
        website.find_element(By.XPATH, '//*[@name="password"]').send_keys(self.credentials['password_pams'])
        website.find_element(By.XPATH, '//button[@data-name="button-login-form"]').click()

        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, '//*[@data-component="partners"]')))

    def open(self, website, pams_id: str) -> (str, str):
        url = 'https://proxy-partner-management-uat.miinto.net/partners'
        sec_part_url = f"/preview/{pams_id}/info" if pams_id and pams_id != "" else "/create/info"

        # Go to edit tab
        if url not in website.current_url:
            website.get(url)
            xpath = '//*[@data-component="partners" or @placeholder="Your password"]'
            WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, xpath)))
            if website.find_elements(By.XPATH, '//*[@name="password"]'):
                self.login(website)

            website.get(url + sec_part_url)
            xpath = '//*[@data-name="preview-primary-core-platform" or @data-name="partner-core-market"]'
            WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, xpath)))

        return url, sec_part_url

    def open_specific_market(self, website, market: str):
        if market == "UK":
            market = "GB"
        elif market == "SHRM":
            market = "PL"

        if chanel := website.find_elements(By.XPATH, f'//div/ol/li/p[text()="{market.upper()}"]'):
            chanel[0].click()
        elif chanel := website.find_elements(By.XPATH, f"//button[@role='tab']/span[text()='{market.upper()}']"):
            chanel[0].click()
        time.sleep(0.5)

        if add_market := website.find_elements(By.XPATH, '//button[@data-name="button-create-market"]'):
            add_market[0].click()
        elif edit_market := website.find_elements(By.XPATH, '//button[@data-name="button-market-or-partner-edit"]'):
            edit_market[0].click()
        time.sleep(1)

    def fill_first_step(self, website, data: dict) -> None:
        select_fields_names['core_market'] = 'partner-core-market'
        website.find_element(By.XPATH, "//input[@name='name']").send_keys(data["Shop_Name"])
        self.fill_select_fields(website, {"core_market": markets[data['market']]})
        del select_fields_names['core_market']

        website.find_element(By.XPATH, '//button[@data-name="button-save-and-next"]').click()
        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, '//input[@name="orderEmail"]')))

    def fill_new_market_fields(self, website, data: dict) -> None:
        if password := website.find_elements(By.XPATH, '//input[@name="password"]'):
            if password[0].is_enabled():
                password[0].send_keys(data["Password"])
                website.find_element(By.XPATH, '//input[@name="passwordRepeat"]').send_keys(data["Password"])

        select_fields_names["Vat_Zone"] = "vatZone"

        if data['Home_Market'] == 'UK':
            self.fill_select_fields(website, {"Vat_Zone": "Foreign"})
        else:
            search_vat_zone = vat_zones.get(data['Home_Market'])
            v_z_value = search_vat_zone[data['market']] if search_vat_zone is not None else 'EU'
            self.fill_select_fields(website, {"Vat_Zone": v_z_value})

        del select_fields_names["Vat_Zone"]

    def fill_tickbox_fields(self, website, data: dict, tick_box_dict: dict = tickbox_class_names) -> None:
        for key, value in tick_box_dict.items():
            if key not in data:
                continue
            time.sleep(0.1)

            element = website.find_element(By.XPATH, f'//input[@data-name="{value}"]/../div/button')
            if data[key] and data[key] != 0 and not element.is_selected():
                element.click()
            elif (not data[key] or data[key] == 0) and element.is_selected():
                element.click()

    def fill_select_fields(self, website, data: dict, select_dict: dict = select_fields_names) -> (str, str):
        for key, value in select_dict.items():
            if key not in data:
                continue
            time.sleep(0.1)

            element = website.find_element(By.XPATH, f'//div[@data-name="{value}"]/button')
            if not element.is_enabled():
                continue

            element.click()
            time.sleep(0.2)

            x = f'//div[@data-name="{value}"]/div/div/div/span/span[text()="{data[key]}"]'
            if option := website.find_elements(By.XPATH, x):
                option[0].click()
            elif "payment_method" in key:
                return "Issue", f"The account number was not updated on [{data['market']}] market, " \
                                                f"due to the lack of '{data[key]}' option in the PaMS. Please provide " \
                                                f"the IBAN & SWIFT number instead."
            elif 'country' in key.lower():
                return "Issue", f"Can`t find the country [{data[key]}] on the Admin`s [{data['market']}]" \
                                                f" market. The field [{key}] cause an issue." \
                                                f" Please make sure that the country field has correct country."
            else:
                raise ValueError(f"Can't find value [{data[key]}] of [{value}].")

        return "Ok", "Ok"

    def fill_input_fields(self, website, data: dict, input_dict: dict = input_fields_names) -> None:
        for key, value in input_dict.items():
            if key not in data or not data[key]:
                continue
            time.sleep(0.1)

            element = website.find_element(By.XPATH, f'//input[@name="{value}"]')
            if not element.is_displayed() or not element.is_enabled():
                continue

            if "shippingAddresses.0.street1" in key:
                element = website.find_element(By.XPATH, '//input[@name="shippingAddresses.0.name"]')
                element.clear()
                element.send_keys(data["Shop_Name"])

            try:
                if key == "Date_of_signing":
                    signup_date = [element.send_keys(i) for i in reversed(str(data[key][0].date()).split("-"))]
                elif key == "Shop_Name" and data['market'] == "CN":
                    element.clear()
                    element.send_keys(f"{data[key]} by Miinto")
                else:
                    element.clear()
                    element.send_keys(data[key])
            except:
                raise ValueError(key, "->>>><<<<< this field has the issue.")

    def get_edit_view_values(self, website) -> dict:
        tickbox_dict = {
            i.get_attribute("data-name"): 'ON' if i.find_element(By.XPATH, "../div/button").is_selected() else "OFF"
            for i in website.find_elements(By.XPATH, "//button/../../input")
        }
        input_dict = {
            name: website.find_element(By.XPATH, f'//input[@name="{name}"]').get_attribute("value")
            for name in input_fields_names.values()
        }
        select_dict = {
            name: website.find_element(By.XPATH, f'//*[@data-name="{name}"]/button/span').get_attribute("innerText")
            for name in select_fields_names.values()
        }

        return tickbox_dict | input_dict | select_dict

    def update_edit_view(self, website, data: dict) -> (str, str):
        self.open(website, data['pams_partner_id'])
        self.open_specific_market(website, data["market"])

        if website.find_elements(By.XPATH, "//div[@data-name='partner-core-market']"):
            self.fill_first_step(website, data)
        if data['market'] in data['all_used_ids'].split(",")[-1]:
            fields_before = {} if "Create core" in data['part_title'] else self.get_edit_view_values(website)

        data['pams_id'] = website.current_url.split("/")[5]

        self.fill_tickbox_fields(website, data)
        self.fill_input_fields(website, data)
        action, comment = self.fill_select_fields(website, data)
        if "Issue" in action:
            return action, comment
        elif 'Create core' in data['part_title'] or 'Other markets' in data['part_title']:
            self.fill_new_market_fields(website, data)

        response = self.save_edit_view(website, data)
        if "error" in response or "Issue" in response:
            return "Issue", response
        elif data['market'] not in data['all_used_ids'].split(",")[-1]:
            return "Success", "Simple comment. (waiting for last market to generate appropriate comment)."

        # GET THE VALUES FROM FIRST SAVED MARKET
        self.open_specific_market(website, data['all_used_ids'].split(",")[0].split("-")[0])
        fields_after = self.get_edit_view_values(website)
        all_f = {**tickbox_class_names, **input_fields_names, **select_fields_names}
        updated_fields = "\n\n".join(f"{i.replace('_', ' ')}:\n---\n\n >[{fields_before.get(all_f[i])}]-->"
                                     f"[{fields_after[all_f[i]]}]" for i in all_f if i in data).replace("None", "")

        return "Success", \
            f"Successfully finished task: [{data['part_title']}].\nWhat was updated?\n\n---\n{updated_fields}"

    def save_edit_view(self, website, data: dict) -> str:
        if save := website.find_elements(By.XPATH, '//button[@data-name="button-on-save-edit-form"]'):
            save[0].click()
        elif data['market'] in data['all_used_ids'].split(",")[-1]:
            save = website.find_elements(By.XPATH, '//button[@data-name="button-finish"]')
            save[0].click()
        elif save := website.find_elements(By.XPATH, '//button[@data-name="button-save-and-next"]'):
            save[0].click()
        else:
            raise NoSuchElementException("Can't find save button in PaMS")

        # Wait for save buttons to be enabled and everything to be saved
        try:
            WebDriverWait(website, 20).until(EC.element_to_be_clickable(save[0]))
        except NoSuchElementException:
            pass
        except StaleElementReferenceException:
            pass
        except TimeoutException:
            comment = f"There was an issue with task [{data['part_title']}].\n\n" \
                      f"(The error refers to PaMS not Podio)\n" \
                      f"Save button in PaMS is loading without any actions."
            return f"{comment}\n\nCouldn't map all created ids in PaMS." \
                   f"You can see it under the link:\n " \
                   f"https://proxy-partner-management-uat.miinto.net/partners/preview/{data['pams_id']}" \
                   if data['part_title'] in ["Other markets", "Create core"] else comment
        time.sleep(1)

        # Get save result
        front_errors = website.find_elements(By.XPATH, "//p[contains(@data-name, 'error')]")
        backend_errors = website.find_elements(By.XPATH, '//div[@id="marketEditErrorModal"]/div/p')

        if front_errors:
            error_message = "\n".join([i.get_attribute("data-name").replace("-", " ") for i in front_errors])
            response = f"There was an issue with task [{data['part_title']}].\n\n" \
                       f"(The error refers to PaMS not Podio)\n" \
                       f"The setup in {data['market']} market has some errors:\n\n ---\n"
            for line in error_message.split("\n"):
                response += "Incorrect field [" + f"]\n --- \n\n > ".join(line.split("error")) + "\n\n"
            response += "\n\n --- \nTo handle this error please fill in the related fields in Podio.\n\n --- "
        elif backend_errors:
            response = f"There was an issue with task [{data['part_title']}].\n\n" \
                       f"(The error refers to PaMS not Podio)\n" \
                       f"The setup in {data['market']} market has some errors:\n\n ---\n" \
                       f"Backend issue \n --- \n\n > {backend_errors[0].text}" \
                       "\n\n --- \nTo handle this error please contact with us.\n\n --- "
        else:
            response = "PaMS was updated"

        return response

    def wait_for_ids(self, website, data: dict) -> (str, str, str):
        time.sleep(2)

        website.get(f"https://proxy-partner-management-uat.miinto.net/partners/preview/{data['pams_id']}")
        xpath = '//*[@data-name="preview-primary-core-platform"]'
        WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.XPATH, xpath)))
        website.find_element(By.XPATH, '//button[@data-name="partner-info"]').click()

        error_comment = \
                    f"There was Issue with the integration in PaMS.\n " \
                    f"Couldn't map all created ids in PaMS.\n\n " \
                    f"You can see it under the link:\n " \
                    f"https://proxy-partner-management-uat.miinto.net/partners/preview/{data['pams_id']}"

        core_market = website.find_element(By.XPATH, '//p[@data-name="preview-primary-core-platform"]').text
        core_market_short = next(key for key, value in markets.items() if value == core_market)
        core_xpath = f'//*[@data-name="shop-id-{"GB" if core_market_short=="UK" else core_market_short}"]'

        with contextlib.suppress(Exception):
            WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.XPATH, core_xpath)))

        website.get(f"https://proxy-partner-management-uat.miinto.net/partners/preview/{data['pams_id']}")
        WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.XPATH, xpath)))

        core_id = website.find_elements(By.XPATH, core_xpath)
        if not core_id or not core_id[0].text.isdigit():
            return [], "Issue", error_comment

        new_ids = []
        for shop_id in data['all_used_ids'].split(","):
            market = shop_id.split("-")[0]
            new_id = website.find_elements(By.XPATH, f'//*[@data-name="shop-id-{"GB" if market=="UK" else market}"]')
            if new_id and new_id[0].text.isdigit():
                new_ids.append(f"{market}-{new_id[0].text}")

        if len(new_ids) != len(data['all_used_ids'].split(",")):
            return new_ids, "Issue", error_comment

        return new_ids, "Success", ""

    def get_shipp_address_values(self, website) -> str:
        buttons = website.find_elements(By.XPATH, '//button[contains(@data-name, "button-shipping-address-")]')[1:]
        elements = [['SHIPPING#', 'NAME', 'STREET1', 'STREET2', 'POSTALCODE', 'CITY', 'COUNTRY']]
        for num, button in enumerate(buttons, 1):
            button.click()
            elements.append([
                website.find_element(By.XPATH, f'//*[@data-name="button-shipping-address-{num}"]').text,
                website.find_element(By.XPATH, f'//*[@name="shippingAddresses.{num}.name"]').get_attribute('value'),
                website.find_element(By.XPATH, f'//*[@name="shippingAddresses.{num}.street1"]').get_attribute('value'),
                website.find_element(By.XPATH, f'//*[@name="shippingAddresses.{num}.street2"]').get_attribute('value'),
                website.find_element(By.XPATH, f'//*[@name="shippingAddresses.{num}.zipCode"]').get_attribute('value'),
                website.find_element(By.XPATH, f'//*[@name="shippingAddresses.{num}.city"]').get_attribute('value'),
                website.find_element(By.XPATH, f'//*[@data-name="shippingAddresses.{num}.country"]/button/span').text
            ])

        text = ""
        for row in elements[1:]:
            text += f"\n\n{row[0]} \n---\n"
            for num, cell in enumerate(row[1:], 1):
                text += f"\n >{elements[0][num]}: [{cell}]"
        return text

    def update_extra_shipp_address(self, website, data: dict) -> (str, str):
        self.open(website, data['pams_partner_id'])
        self.open_specific_market(website, data["market"])

        # DELETE EXISTING ADDRESSES
        buttons = website.find_elements(By.XPATH, '//button[contains(@data-name, "button-shipping-address-")]')[1:]
        for _ in buttons:
            website.find_elements(By.XPATH, '//button[contains(@data-name, "button-shipping-address-")]')[-1].click()
            website.find_element(By.XPATH, '//button[@data-name="button-remove-shipping-address"]').click()

        time.sleep(5)

        # ADD NEW ADDRESSES
        for num, address_num in enumerate(data["shipping_locations"], 1):
            website.find_element(By.XPATH, '//button[@data-name="button-add-shipping-address"]').click()
            website.find_elements(By.XPATH, '//button[contains(@data-name, "button-shipping-address-")]')[-1].click()

            address_dict = data["shipping_locations"][address_num]
            self.fill_select_fields(website, address_dict, {'countrycode': f'shippingAddresses.{num}.country',
                                                            'market': data['market']})
            self.fill_input_fields(website, address_dict,
                                   {'name': f'shippingAddresses.{num}.name',
                                    'street': f'shippingAddresses.{num}.street1',
                                    'street2': f'shippingAddresses.{num}.street2',
                                    'zipcode': f'shippingAddresses.{num}.zipCode',
                                    'city': f'shippingAddresses.{num}.city'})

        response = self.save_edit_view(website, data)
        if "error" in response:
            return "Issue", response

        self.open_specific_market(website, data["market"])
        values = self.get_shipp_address_values(website)

        return "Success", f"Successfully finished adding the additional shipping locations to Admin.\n" \
                          f"What was updated?\n\n---\n" + values
