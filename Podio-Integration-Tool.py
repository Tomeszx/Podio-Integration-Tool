#!venv/bin/python3.9
import contextlib
import random
import warnings
import json
import os
import re
import threading
import time
import gspread
import pycountry
import requests

import gspread_dataframe as gd
import pandas as pd

from datetime import datetime
from multiprocessing import Pool
from gooey import Gooey, GooeyParser
from selenium import webdriver
from bs4 import MarkupResemblesLocatorWarning
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup as bs
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from oauth2client.service_account import ServiceAccountCredentials
from test_podio_data import test_data

login, api_calls_stats = {}, {}
select_fields_names = json.load(open("Podio & PAMS fields/select_fields_names.json"))
input_fields_names = json.load(open("Podio & PAMS fields/input_fields_names.json"))
tickbox_class_names = json.load(open("Podio & PAMS fields/tickbox_class_names.json"))
vat_zones = pd.read_csv('Vat Zones/vat_zones.csv', index_col=0)
login_default = json.load(open("Credentials/config.json"))
markets = {"NL": "Netherlands", "DK": "Denmark", "SE": "Sweden", "BE": "Belgium", "FR": "France",
           "IT": "Italy", "ES": "Spain", "DE": "Germany", "PL": "Poland", "UK": "United Kingdom",
           "FI": "Finland", "CN": "China", "NO": "Norway"}


def main(website, tasks_list: dict, comment_period: int, tasks_dict: dict, access_tokens: list) -> None:
    for task_row in tasks_list:
        data = {"tasks_keys": tasks_dict, 'comment_period': comment_period}
        data |= task_row

        if "vintage" in data['partner_type']:
            data['partner_type'] = "partners"

        print(f"\n{'':^40}>>>>>>>> {data['Partner_Name']} {data['task_text']} <<<<<<<<<<")

        podio = Podio(data, access_tokens)
        comment, data = podio.prepare_data()
        podio.data = data

        if (podio.limit - podio.remaining) / podio.limit >= 0.80:
            try:
                podio.access_tokens.pop(0)
            except IndexError:
                print("You have almost exceed the API rate limit. Try again for one hour.")
                return

        if (comment is False or "Username" in comment) and "Create core" in data['part_title']:
            action, comment = podio.add_username_password()
            if not podio.data['files']:
                action, comment = "Issue", "Can`t create admins because PDF contract is not attched to the Podio."
            if "Issue" in action:
                print(podio.add_error_comment(comment))
                continue
        elif comment is not False and "go to next task" in comment:
            continue
        elif comment is not False:
            print(podio.add_error_comment(comment))
            continue

        # Choosing task
        if 'pc location' in data['part_title'].lower():
            ProductService().create_pc_location(website, data)
            action, comment = ProductService().add_aliases(website, data)

        elif 'add aliases' in data['part_title'].lower():
            action, comment = ProductService().add_aliases(website, data)

        # Update Admins
        else:
            action, comment = admin_tasks(website, podio, data)

        # Update Podio with comment and click tickbox if needed
        if "Issue" in action or "error" in comment:
            print(podio.add_error_comment(comment))
            if action == "Issue, but click tickbox":
                podio.complete_task(website)
        elif action == "Success":
            podio.complete_task()
            print(podio.add_comment(comment))
        else:
            raise ValueError("Undefined action happened.")


def admin_tasks(website, podio, data: dict) -> (str, str):
    # Check and exclude markets that need to be added
    if data['part_title'] in ["Check id's in PAMS", "Other markets", "Create core"]:
        all_shop_ids = ""
        for i in data['Markets_to_activate_for_the_partner']:
            if i + "-" not in data['All_Shop_IDs']:
                i = i.replace("SHWRM", "PL")
                all_shop_ids += f',{i}-create' if len(all_shop_ids) > 0 else f'{i}-create'

        if all_shop_ids.count("-create") == 0:
            return "Issue, but click tickbox", "There are no new markets to add for this Partner."
        elif "create core" in data['part_title'].lower():
            all_shop_ids = ",".join(podio.sort_core_as_first(all_shop_ids.split(",")))
        elif "other market" in data['part_title'].lower():
            all_shop_ids = all_shop_ids.replace("create", "add_market")
    else:
        all_shop_ids = data['All_Shop_IDs']

    data['all_used_ids'] = all_shop_ids
    # Update information in all markets one by one
    for shop_id in all_shop_ids.split(","):
        data['market'] = shop_id.split("-")[0]
        data['id'] = shop_id.split("-")[1]

        if "Check id's in PAMS" in data['part_title']:
            PAMS().open(website, data["pams_partner_id"])
            data['pams_id'] = data["pams_partner_id"]
            new_ids, action, comment = PAMS().wait_for_ids(website, data)
            podio.add_new_shop_ids(new_ids, data['pams_id'])
            action = "Success"
            if "Issue" in comment:
                action = "Issue"
            break

        elif 'Additional shipping locations' in data['part_title']:
            action, comment = PAMS().update_extra_shipp_address(website, data)

        elif 'Return address' in data['part_title']:
            data |= data["shipping_locations"]["Return 0"]
            action, comment = PAMS().update_edit_view(website, data)

        elif "commission" in data['part_title'].lower().replace(" ", ""):
            if data['market'] == "CN":
                continue
            if data.get('commission_values') is None:
                data['commission_values'] = []
            action, comment = Admin().update_commission(website, data)

        elif "IBAN" in data['part_title'] or "Other markets" in data['part_title'] \
                or "create core" in data['part_title'].lower() or "all fields" in data['part_title']:

            data['payment_method'], m = "IBAN/SWIFT", data['market']
            if "Multiple IBANs" in data:
                if data.get(f"IBAN {m}") and data.get(f"SWIFT {m}"):
                    data['Bank_Account_Number_-_IBAN_(format:_PL123456789)'] = data[f"IBAN {m}"]
                    data['Bank_Account_Number_-_SWIFT'] = data[f"SWIFT {m}"]
                elif data.get(f"Account {m}") and data.get(f"CODE {m}"):
                    data['Bank_Account_Number_-_IBAN_(format:_PL123456789)'] = data[f"Account {m}"]
                    data['Bank_Account_Number_-_SWIFT'] = data[f"CODE {m}"]
                    data['payment_method'] = "Bank transfer"
                else:
                    comment = f"The wrong format, probably missing market in IBAN/SWIFT. " \
                              f"\nCheck if [{data['market']}] is included in the field."
                    return "Issue", comment

            action, comment = PAMS().update_edit_view(website, data)

            if "Issue" in action:
                if "Create core" in data['part_title']:
                    podio.add_new_shop_ids([], data['pams_id'])
                return "Issue", comment
            elif "Create core" in data['part_title'] and shop_id == all_shop_ids.split(",")[-1]:
                new_ids, action, err_comment = PAMS().wait_for_ids(website, data)
                podio.add_new_shop_ids(new_ids, data['pams_id'])
                if err_comment:
                    return "Issue", err_comment
            elif "other market" in data['part_title'].lower() and shop_id == all_shop_ids.split(",")[-1]:
                new_ids, action, err_comment = PAMS().wait_for_ids(website, data)
                podio.add_new_shop_ids(new_ids, data['pams_id'])
                if err_comment:
                    return "Issue", err_comment
        else:
            action, comment = PAMS().update_edit_view(website, data)

        if "Issue" in action or "error" in comment:
            return action, comment

    return action, comment


class Podio:
    def __init__(self, data: dict, access_tokens: list):
        self.access_tokens = access_tokens
        self.data = data

    def __get_access_token__(self, client_id: str, client_secret: str) -> str:
        # Set the client ID, client secret, username, and password
        data = {
            'grant_type': 'password',
            'client_id': client_id,
            'client_secret': client_secret,
            'username': login['username_podio'],
            'password': login['password_podio']
        }

        # Make the HTTP request to obtain the access token
        response = requests.post('https://podio.com/oauth/token', data=data)

        # Parse the response from the Podio API
        data = response.json()

        if response.status_code != 200:
            raise ConnectionRefusedError(data["error_description"])

        limit = int(response.headers.get('X-Rate-Limit-Limit'))
        remaining = int(response.headers.get('X-Rate-Limit-Remaining'))
        api_calls_stats[f"Max api calls [{limit}]"] = f"You've made [{limit-remaining}] Api calls"

        # return the access token from the response
        return data['access_token']

    def __send_request__(self, method: str, sec_part_url: str, data=None, params=None) -> dict:
        response = requests.request(
            method,
            f"https://api.podio.com/{sec_part_url}",
            headers={'Authorization': f'Bearer {self.access_tokens[0]}'},
            json=data,
            params=params,
        )
        self.limit = int(response.headers.get('X-Rate-Limit-Limit'))
        self.remaining = int(response.headers.get('X-Rate-Limit-Remaining'))
        api_calls_stats[f"Max api calls [{self.limit}]"] = f"You've made [{self.limit-self.remaining}] Api calls"
        return response.json() if response.status_code == 200 else {}

    def __delete_task__(self, task_id: str) -> dict:
        return self.__send_request__(method='delete', sec_part_url=f'task/{task_id}')

    def __update_field__(self, field_id: str, value: str, item_id=None) -> dict:
        item_id = self.data['shop_item_id'] if item_id is None else item_id

        return self.__send_request__('put', f'item/{item_id}/value/{field_id}', data={"value": value})

    def __search_for_user__(self, user_name: str) -> str:
        response = self.__send_request__('get', 'search/v2', params={'query': user_name, 'ref_type': 'profile',
                                                                    'limit': 2})
        return ([f"{result['link'].split('/')[-1]}"
                 for result in response['results'] if user_name == result['title']][0] if response else "")

    def __process_list_of_tasks__(self, tasks_list: list[dict], tasks_keys: dict) -> list:
        tasks = {}
        for task in tasks_list:
            full_title = f'{task["Partner_Name"]} {task["task_text"]}'
            if "Add commission" not in tasks_keys and "Add commission" in task["task_text"]:
                continue
            elif full_title in tasks:
                self.__delete_task__(task['task_id'])
            else:
                tasks[full_title] = task

        print(f"{'':^60}", " Tasks for the BOT ->", len(list(tasks.values())), f"{'':_^100}\n\n")

        return list(tasks.values())

    def get_tasks(self, tasks_keys: dict, responsible_id: str = '6461478') -> list[dict]:
        tasks_list = []
        number_tasks = 0
        tasks_summary = self.__send_request__('GET', 'task/total/')['own']
        with Pool() as pool:
            results = []

            for offset in range(0, tasks_summary['later'], 100):
                params = {'responsible': responsible_id, 'completed': False, 'offset': offset, 'limit': 100}
                results.append(pool.apply_async(self.__send_request__, ('GET', 'task/', None, params)))

            for result in results:
                response = result.get()
                number_tasks += len(response)
                tasks_list.extend(
                    {
                        'task_id': task['task_id'],
                        'task_text': task['text'],
                        'shop_item_id': task['ref']['data']['item_id'],
                        'Partner_Name': task['ref']['data']['title'],
                        'part_title': task_to_do,
                        'partner_type': task['ref']['data']['app']['config']['name'].lower(),
                        'link_to_shop': task['ref']['data']['link'],
                        'task_requester': task['description']
                    }
                    for task in response if response
                    for task_to_do in tasks_keys if task_to_do in task['text']
                    if "PAMS TEST " in task['ref']['data']['title']  # Usun
                )
        print(f'{"":_^100}\n\n', f"{'':^60}", f"Number of tasks in Podio -> {number_tasks}")
        print(f"{'':^60}", f" Tasks done yesterday -> {tasks_summary['completed_yesterday']}\n")

        return self.__process_list_of_tasks__(tasks_list, tasks_keys)

    def get_partner_details(self, item_id=None) -> dict[str, any]:
        item_id = self.data['shop_item_id'] if item_id is None else item_id

        response = self.__send_request__(method='get', sec_part_url=f'item/{item_id}')
        data = {'fields': {}, "fields_ids": {}, 'comments': []}

        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
        for field in response['fields']:
            key = field['label'].strip().replace(" ", "_")
            if key not in self.data['tasks_keys'][self.data['part_title']]:
                continue
            data["fields_ids"][key] = field['field_id']
            if field['type'] == 'contact':
                data[key] = [value['value'] for value in field['values']]
            elif field['type'] == 'date':
                data[key] = [datetime.strptime(value['start_date'], "%Y-%m-%d") for value in field['values']]
            elif field['type'] == 'category' and field['config']['settings']['multiple'] is True:
                data[key] = [value['value']['text'] for value in field['values']]
            elif field['type'] == 'category':
                data[key] = [value['value']['text'] for value in field['values']][0]
            elif field['type'] == 'email':
                data[key] = [value['value'] for value in field['values'][:5]]
            elif field['type'] in ['text', 'number', 'phone', 'calculation']:
                data[key] = [value['value'] for value in field['values']][0]
                data[key] = bs(data[key], 'html.parser').get_text().replace("\xa0", " ")

        for comment in response['comments']:
            if comment['created_by']["name"] == "Update Admins":
                data['comments'].append({'date': comment['created_on'], 'value': comment['value']})

        for files in response['files']:
            data['files'] = ".pdf" in files["name"]

        return data

    def prepare_data(self) -> (str, dict):
        task_dict = self.data['tasks_keys'][self.data['part_title']]

        # Get dict with all needed information from Podio
        podio_data = self.get_partner_details()

        # Test the data (that all elements in the dict are in the correct format)
        comment, new_id, error = test_data(podio_data, task_dict, self.data)
        print("There is an issue") if comment else print("The data looks good!")

        # If there is an issue with formatting then send comment to Podio and go to next task
        if "wrong format" in error:
            if "There are no new shops to create." in comment:
                self.complete_task(self.data['task_id'])
            return comment, self.data | podio_data
        return comment, self.data | podio_data

    def add_username_password(self) -> (str, str):
        fields_ids = ['222617769', '193610265'] \
            if self.data['partner_type'] == "brands"\
            else ["188759350", "188759351"]

        self.__update_field__(fields_ids[0], self.data['Username'])
        self.__update_field__(fields_ids[1], self.data['Password'])

        return "", ""

    def add_new_shop_ids(self, new_ids: list, pams_id: str) -> None:
        fields_ids = ["251071111", "193610233"] \
            if self.data['partner_type'] == "brands" \
            else ["249863352", "187361639"]
        
        print(self.__update_field__(fields_ids[0], pams_id))

        if new_ids:
            podio_data = self.get_partner_details()
            new_id_field = podio_data['All_Shop_IDs'].split(",") if podio_data.get("All_Shop_IDs") else []
            new_id_field.extend(new_ids)
            if self.data['part_title'] == "Create core" or \
                    (self.data['part_title'] == "Check id's in PAMS" and not podio_data.get("All_Shop_IDs")):
                new_id_field = self.sort_core_as_first(new_id_field)
            new_list = ','.join([x for i, x in enumerate(new_id_field) if x not in new_id_field[:i]])

            self.__update_field__(fields_ids[1], new_list)

    def sort_core_as_first(self, all_shop_ids: list[str], home_market=None) -> list[str]:
        home_market = self.data['Home_Market'] if home_market is None else home_market
        markets_prefix = [i.split("-")[0] for i in all_shop_ids]

        if home_market.upper() in {'DK', 'SE', 'NL', 'BE', 'PL', 'CH', 'NO'} and home_market.upper() in markets_prefix:
            all_shop_ids.insert(0, all_shop_ids.pop(
                all_shop_ids.index(*[x for x in all_shop_ids if re.search(home_market, x)])))
        elif "NL" in markets_prefix:
            all_shop_ids.insert(0,
                                all_shop_ids.pop(all_shop_ids.index(*[x for x in all_shop_ids if re.search('NL', x)])))
        else:
            core_priority = [i for i in ["DK", "BE", "NO", "SE"] if i in markets_prefix]
            all_shop_ids.insert(0, all_shop_ids.pop(
                all_shop_ids.index(*[x for x in all_shop_ids if re.search(core_priority[0], x)])))

        return all_shop_ids

    def complete_task(self, task_id=None, complete_action: bool = True) -> dict:
        task_id = self.data['task_id'] if task_id is None else task_id

        return self.__send_request__(method='put', sec_part_url=f'task/{task_id}', data={"completed": complete_action})

    def add_comment(self, value: str, item_id=None) -> str:
        item_id = self.data['shop_item_id'] if item_id is None else item_id
        user_id = self.__search_for_user__(self.data['task_requester'])
        msg = f"@[{self.data['task_requester']}](user:{user_id})\n\n{value}" if user_id else value

        table = pd.DataFrame([[self.data["Partner_Name"], self.data['part_title'], value,
                               self.data["link_to_shop"], datetime.now()]])
        GoogleSheet().send_data(col=1, sheet_name="Bot msgs", data=table)

        return self.__send_request__('post', f'comment/item/{item_id}/', data={"value": msg})['rich_value']

    def add_error_comment(self, comment: str) -> str:
        check = re.sub('[^a-zA-Z0-9]', '', comment).lower()

        for podio_comment in self.data['comments']:
            comm_date = datetime.strptime(podio_comment["date"].split()[0], "%Y-%m-%d").date()
            com_text = re.sub('[^a-zA-Z0-9]', '', podio_comment['value']).lower()
            if (datetime.now().date() - comm_date).days < self.data['comment_period'] and check in com_text:
                return 'Comment not added. (Duplicate).'
        return self.add_comment(comment)


class Admin:
    def __init__(self):
        self.vat_rate = {'SE': 25, 'DE': 19, 'DK': 25, 'BE': 21, 'PL': 23, "SHWRM": 23, 'NL': 21, 'IT': 22,
                         'ES': 21, 'FR': 20, 'FI': 24, 'NO': 25, 'UK': 20, 'CH': 7.7}
        self.addi_shipping_fields = ['zipcode', 'name', 'street', 'street2', 'city']

    def login(self, website, market: str, url: str, sec_part_url: str):
        website.find_element(By.XPATH, '//*[@id="username"]').send_keys(login['username_admin'])
        website.find_element(By.XPATH, '//*[@id="password"]').send_keys(login['password_admin'])
        website.find_element(By.XPATH, '/html/body/div[2]/div/div/form/fieldset/div[4]/div/input[2]').click()
        if market.lower() == 'cn':
            xpath = '//button[@class="btn btn-mini login-user pull-right"]'
            WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, xpath)))
            website.find_element(By.XPATH, xpath).click()
            time.sleep(2)

        website.get(url + sec_part_url)

        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.NAME, 'contactperson1')))

    def open(self, website, market: str, id: str) -> (str, str):
        if market.lower() in {'pl', 'shwrm'}:
            url = 'https://www.showroom.pl/'
        elif market.lower() == 'uk':
            url = 'https://www.miinto.co.uk/'
        elif market.lower() == 'cn':
            url = 'https://china.miinto.net/'
        else:
            url = f'https://www.miinto.{market.lower()}/'

        # Go to edit tab
        sec_part_url = f'admin/shops-edit.php?action=edit&id={id}'
        website.get(url + sec_part_url)
        start = datetime.now()
        while not website.find_elements(By.NAME, 'contactperson1') and not website.find_elements(By.ID, "password"):
            time.sleep(0.5)
            if (datetime.now() - start).total_seconds() > 5:
                website.get(url + sec_part_url)
                time.sleep(2)

        if website.find_elements(By.XPATH, '//*[@id="password"]'):
            self.login(website, market, url, sec_part_url)
        return url, sec_part_url

    def update_commission(self, website, data: dict) -> (str, str):
        partner_type_box = {"partners": ["Name: Shop", "Store-"], "brands": ["Name: Brand", "Brand-"]}
        website.switch_to.window(website.window_handles[3])
        url, sec_part = self.open(website, data['market'], data['id'])

        pure_comm = data['Pure_commission_to_be_charged_on_balanced_orders']
        new_comm = round(float(pure_comm) * ((self.vat_rate[data['market']] / 100) + 1), 2)

        reducer_type_field = Select(website.find_element(By.XPATH, '//select[@name="commission_reducer_type"]'))
        prev_reucer = reducer_type_field.first_selected_option.get_attribute("value")
        shop_name = website.find_element(By.XPATH, '//input[@name="shopname"]').get_attribute("value")
        partner_type = Select(
            website.find_element(By.XPATH, '//select[@name="admin"]')).first_selected_option.text.lower()
        full_name = f'{shop_name} ({partner_type}) ({prev_reucer})'

        # Go to commission tool
        if len(website.window_handles) < 5:
            website.execute_script("window.open()")
        website.switch_to.window(website.window_handles[4])
        website.get(url + 'admin/tools/commission')
        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, '//span[@title="Edit"]')))

        # Find the correct column and box to drag it
        drag = [i for i in website.find_elements(By.XPATH, f"//li[contains(@data-default-block-type, "
                                                           f"'{partner_type_box['partners'][1]}')]")][0]

        xpath = '//div[@class="commission-tools__block js-rules-list"]'
        try:
            drop = [i for i in website.find_elements(By.XPATH, xpath) if partner_type_box[
                data['partner_type']][0].lower().replace(" ", "") in i.text.lower().replace(" ", "")][0]
        except Exception:
            drop = [i for i in website.find_elements(By.XPATH, xpath) if partner_type_box[
                "partners"][0].lower().replace(" ", "") in i.text.lower().replace(" ", "")][0]

        drop_offset = {"x": drop.location['x'] - drag.location['x'], "y": drop.location['y'] - drag.location['y'] + 115}
        column_width = {"left": drop.location["x"] - 14, "right": drop.location["x"] + drop.size["width"] + 52}
        default_commission = drop.find_elements(By.XPATH, './/span[@class="commission-tools__block-title"]')[1].text

        try:
            if "'" in full_name:
                all_shops = website.find_elements(By.XPATH, f'//span[text()="{full_name}"]')
            else:
                all_shops = website.find_elements(By.XPATH, f"//span[text()='{full_name}']")

            for shop in all_shops:
                get_parent = shop.find_element(By.XPATH, '../../../.')
                if column_width['left'] < get_parent.location["x"] < column_width['right']:
                    open_edit_view_2 = get_parent.find_element(By.XPATH, './/span[@title="Edit"]')
                    open_edit_view_2.click()

                    dropdown = website.find_element(By.XPATH, '//*[@id="ruleForm"]/span/span[1]/span/span[2]')
                    dropdown.click()
                    shop = website.find_element(By.XPATH, "//li[@aria-selected='true']")

                    if shop.get_attribute('id').split("-")[-1] == data['id']:
                        break

                close_edit = website.find_element(By.XPATH, '//*[@id="ruleForm"]/div/input[2]').click()

            else:
                if not all_shops or shop.get_attribute('id').split("-")[-1] != data['id']:
                    raise ValueError(f"Can`t find shop id in commission tool - market [{data['market']}]")

        except Exception:
            print("create new commission box for the new shop.")
            ActionChains(website).drag_and_drop_by_offset(drag, drop_offset["x"], drop_offset["y"]).perform()

            WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, '//*[@id="ruleForm"]')))

            try:
                dropdown = website.find_element(By.XPATH, '//*[@id="ruleForm"]/span/span[1]/span/span[2]')
                dropdown.click()
            except:
                print("ERRORRRRRRR")
                raise ValueError("ERRRRR")

            all_shops = website.find_elements(By.XPATH, f'//li[text()="{full_name}"]')
            shop = [i for i in all_shops if i.get_attribute('id').split("-")[-1] == data['id']][0]
            shop.click()

        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, '//*[@id="ruleForm"]/input[1]')))
        name = website.find_element(By.XPATH, '//*[@id="ruleForm"]/input[1]')
        name.clear()
        name.send_keys(data['Shop_Name'])

        commission_value = website.find_element(By.XPATH, '//*[@id="ruleForm"]/input[2]')
        old_com = commission_value.get_attribute("value")
        commission_value.clear()
        commission_value.send_keys(f'{new_comm}')

        acc = WebDriverWait(website, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="ruleForm"]/div/input[1]')))
        try:
            acc.click()
            WebDriverWait(website, 10).until_not(EC.presence_of_element_located((By.ID, "ruleForm")))
        except Exception:
            website.execute_script("arguments[0].click();", acc)
            WebDriverWait(website, 10).until_not(EC.presence_of_element_located((By.ID, "ruleForm")))

        save_changes = website.find_element(By.XPATH, '//*[@id="main-form"]/button')
        website.execute_script("arguments[0].click();", save_changes)

        while website.find_element(By.XPATH, '/html/body/div[2]/div[2]/div[2]/div[3]/div[3]/span').is_displayed():
            time.sleep(1)
            if save_changes.is_displayed():
                website.execute_script("arguments[0].click();", save_changes)

        xpath = '//span[@class="commission-tools__block-title"]'
        all_d_comm = {float(i.text.split(" ")[0]) for i in website.find_elements(By.XPATH, xpath) if "%" in i.text}

        if max(all_d_comm) >= float(new_comm) >= min(all_d_comm):
            if max(all_d_comm) > float(default_commission.split(" ")[0]):
                reducer_type = "Minimum"
            elif max(all_d_comm) == float(default_commission.split(" ")[0]):
                reducer_type = "Maximum"
        elif float(new_comm) < float(default_commission.replace(' %', '')):
            reducer_type = "Minimum"
        elif float(new_comm) > float(default_commission.replace(' %', '')):
            reducer_type = "Maximum"

        website.execute_script("window.open()")
        website.switch_to.window(website.window_handles[5])
        data['reducerType'] = reducer_type
        action, comment = PAMS().update_edit_view(website, data)
        if "issue" in action.lower() or "issue" in comment.lower():
            return action, comment

        data['commission_values'].append(f" >{data['market']} ({self.vat_rate[data['market']]}%VAT): "
                                              f"[{old_com}%] {prev_reucer}->[{new_comm}%] {reducer_type}\n")

        comment = \
            f"Successfully finished updating commission in Admin.\n" \
            f"What was updated?\n\n---\n" \
            f"\nCommission was changed to\n---\n > [{data['Pure_commission_to_be_charged_on_balanced_orders']}]" \
            f"\n\nCommission value incl. VAT:\n---\n" \
            + "\n\n".join(data['commission_values'])
        return "Success", comment


class PAMS:
    def login(self, website):
        website.find_element(By.XPATH, '//*[@name="username"]').send_keys(login['username_pams'])
        website.find_element(By.XPATH, '//*[@name="password"]').send_keys(login['password_pams'])
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
                                                f"due to the lack of '{data[key]}' option in the PAMS. Please provide " \
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
            raise NoSuchElementException("Can't find save button in PAMS")

        # Wait for save buttons to be enabled and everything to be saved
        try:
            WebDriverWait(website, 20).until(EC.element_to_be_clickable(save[0]))
        except NoSuchElementException:
            pass
        except StaleElementReferenceException:
            pass
        except TimeoutException:
            comment = f"There was an issue with task [{data['part_title']}].\n\n" \
                      f"(The error refers to PAMS not Podio)\n" \
                      f"Save button in PAMS is loading without any actions."
            return f"{comment}\n\nCouldn't map all created ids in PAMS." \
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
                       f"(The error refers to PAMS not Podio)\n" \
                       f"The setup in {data['market']} market has some errors:\n\n ---\n"
            for line in error_message.split("\n"):
                response += "Incorrect field [" + f"]\n --- \n\n > ".join(line.split("error")) + "\n\n"
            response += "\n\n --- \nTo handle this error please fill in the related fields in Podio.\n\n --- "
        elif backend_errors:
            response = f"There was an issue with task [{data['part_title']}].\n\n" \
                       f"(The error refers to PAMS not Podio)\n" \
                       f"The setup in {data['market']} market has some errors:\n\n ---\n" \
                       f"Backend issue \n --- \n\n > {backend_errors[0].text}" \
                       "\n\n --- \nTo handle this error please contact with us.\n\n --- "
        else:
            response = "PAMS was updated"

        return response

    def wait_for_ids(self, website, data: dict) -> (str, str, str):
        time.sleep(2)

        website.get(f"https://proxy-partner-management-uat.miinto.net/partners/preview/{data['pams_id']}")
        xpath = '//*[@data-name="preview-primary-core-platform"]'
        WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.XPATH, xpath)))
        website.find_element(By.XPATH, '//button[@data-name="partner-info"]').click()

        error_comment = \
                    f"There was Issue with the integration in PAMS.\n " \
                    f"Couldn't map all created ids in PAMS.\n\n " \
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


class ProductService:
    def __init__(self):
        self.dict_location = {'DK': '045', 'SE': '046', 'NO': '047', 'NL': '031', 'BE': '032',
                              'PL': '048', 'CH': '041', 'ES': '034', 'IT': '039', 'FI': '358',
                              'FR': '033', 'DE': '049', 'UK': '044', 'CN': '086'}

    def open_pc(self, website) -> None:
        website.get('https://proxy-product.miinto.net/auth/login')
        while not website.find_elements(By.XPATH, '//*[@id="username"]') \
                and not website.find_elements(By.XPATH, "//h1[contains(text(), 'Products')]"):
            time.sleep(0.5)

        if website.find_elements(By.XPATH, '//*[@id="username"]'):
            website.find_element(By.XPATH, '//*[@id="username"]').send_keys(login['username_pc'])
            website.find_element(By.XPATH, '//*[@id="password"]').send_keys(login['password_pc'])
            website.find_element(By.XPATH, '//*[@type="submit"]').click()
            WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, '//table')))

    def create_pc_location(self, website, data: dict) -> (str, str):
        website.switch_to.window(website.window_handles[2])

        if "PC_location_name" in data:
            return "Issue, but click tickbox", "The location is created already"

        primary_id = data["All_Shop_IDs"].split(",")[0].split("-")[1]
        primary_market = data["All_Shop_IDs"].split(",")[0].split("-")[0]

        prefix = "S" if data["partner_type"] == "partners" else "B"
        data["PC_location_name"] = f'{data["Home_Market"]}-{prefix} {data["Shop_Name"]} {primary_id}'

        pc_frame = website.find_element(By.XPATH, '//*[@id="pc-location-name"]/div[1]/div[2]/div/div')
        pc_frame.click()
        iframe = website.find_element(By.XPATH, '//iframe')
        website.switch_to.frame(iframe)

        pc_input = website.find_element(By.XPATH, '//*[@id="tinymce"]/p')
        pc_input.send_keys(data["PC_location_name"])

        website.switch_to.default_content()
        website.find_element(By.XPATH, '//*[@id="pc-location-name"]/div[1]/div[1]/div/div[2]').click()

        website.execute_script("window.open()")
        website.switch_to.window(website.window_handles[4])
        self.open_pc(website)

        website.get('https://proxy-product.miinto.net/location')
        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, "//h1[text() = 'Create Location']")))

        loc_name = website.find_element(By.XPATH, '//input[@id="locationName"]')
        loc_name.send_keys(data["PC_location_name"])

        unified_loc_id = website.find_element(By.XPATH, '//input[@id="locationUnifiedId"]')
        unified_loc_id.send_keys(f"1-m!i!s-{self.dict_location[primary_market]}-{primary_id}")

        website.find_element(By.XPATH, "/html/body/div[1]/div/main/form/div[2]/span").click()
        country = pycountry.countries.get(alpha_2=primary_market)
        language = pycountry.languages.get(alpha_2=data['Home_Market'])

        try:
            select_country = website.find_element(By.XPATH, f"//li[text()='{country.name}']").click()
        except:
            raise ValueError(f"{country} - Cant find country.")

        website.find_element(By.XPATH, "/html/body/div[1]/div/main/form/div[3]/span/span[1]/span").click()

        select_language = website.find_elements(By.XPATH, '//li[@class="select2-results__option"]')
        try:
            select_language = website.find_element(By.XPATH, f"//li[text()='{language.name}']").click()
        except Exception:
            select_language = website.find_element(By.XPATH, "//li[text()='English']").click()

        active = website.find_element(By.XPATH, '//*[@id="locationIsActive"]')
        website.execute_script("arguments[0].setAttribute('checked',arguments[1])", active, "checked")

        submit = website.find_element(By.XPATH, '/html/body/div[1]/div/main/form/div[6]/button').click()

        return unified_loc_id

    def add_aliases(self, website, data: dict) -> (str, str):
        website.switch_to.window(website.window_handles[3])
        self.open_pc(website)

        if "PC_location_name" not in data.keys():
            return "Issue", "PC location name is blank or incorrect"

        website.get('https://proxy-product.miinto.net/locations')
        WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.XPATH,
                                                                           "//h1[contains(text(), 'Locations')]")))

        try:
            while data["PC_location_name"] not in website.find_element(By.XPATH, '//tbody').get_attribute(
                    "textContent"):
                next_page = website.find_element(By.XPATH, '//*[@class="feather feather-chevron-right"]').click()
                time.sleep(0.2)
        except Exception:
            comment = "error: Can`t find Pc location name in PC."
            return "Issue", comment

        cells = website.find_elements(By.XPATH, '//tr')
        edit_link = [i.find_element(By.XPATH, './/a[@class="btn btn-outline-primary"]').get_attribute("href")
                     for i in cells if data["PC_location_name"] in i.get_attribute("textContent")][0]

        while True:
            try:
                website.get(edit_link)
                WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.ID, "nav-alias-tab")))

                # Collect existing locations
                website.find_element(By.XPATH, '//button[@id="nav-alias-tab"]').click()
                xpath = "//a[text() = 'Create Location alias']"
                WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.XPATH, xpath)))
                existing_loc = [i.get_attribute("textContent").split("-")[-1] for i in
                                website.find_elements(By.XPATH, '//td') if
                                "1-m!i!s" in i.get_attribute("textContent")]

                for i, shop_id in enumerate(data["All_Shop_IDs"].split(",")):
                    market, market_id = shop_id.split("-")[0], shop_id.split("-")[1]
                    unifed_loc = f"1-m!i!s-{self.dict_location[market]}-{market_id}"

                    # Aliass
                    website.get(f"{edit_link}/alias")
                    WebDriverWait(website, 10).until(EC.presence_of_element_located((By.ID, "locationAliasUnifiedId")))

                    if i > 0 and market_id not in existing_loc:
                        unified_id = website.find_element(By.XPATH, '//*[@id="locationAliasUnifiedId"]')
                        unified_id.send_keys(unifed_loc)

                        website.find_element(By.XPATH, '/html/body/div[1]/div/main/form/div[2]/button').click()
                        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.ID, "nav-alias-tab")))
                break
            except Exception:
                continue

        # Response
        website.get(edit_link)
        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.ID, "nav-alias-tab")))

        website.find_element(By.XPATH, '//button[@id="nav-alias-tab"]').click()
        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.TAG_NAME, "td")))

        existing_loc = ""
        for i in website.find_elements(By.XPATH, '//td'):
            if "1-m!i!s" in i.get_attribute("textContent"):
                loc_id = i.get_attribute("textContent")
                market_loc = [k for k, v in self.dict_location.items() if v == loc_id.split("-")[-2]]
                existing_loc += f"\n >{market_loc} --> [{loc_id}]"
        main_country = website.find_element(By.ID, 'select2-locationCountryId-container').get_attribute("title")
        main_id = website.find_element(By.ID, 'unifiedLocationId').get_attribute("value")

        return "Success", f"Successfully finished update location in PC - Product service.\n" \
                          f"What was updated?\n\n---\n\n " \
                          f"\n > \n Main location:\n---\n >[{main_country}]-->[{main_id}]\n\n" \
                          f" >Active Aliases:\n---\n {existing_loc}"


class GoogleSheet:
    def send_data(self, col: int, sheet_name: str, data: [list]) -> None:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name('Credentials/client_secret.json', scope)
        client = gspread.authorize(creds)

        url = "https://docs.google.com/spreadsheets/d/1Kw8t5Cdfi4zhw8JbBOE6wNyYfgxvoQDXAcQxsguLMu4/edit#gid=0"
        spread_sheet = client.open_by_url(url)
        sheet = spread_sheet.worksheet(sheet_name)

        if sheet_name == "Tasks":
            spread_sheet.values_clear("Tasks!A2:D")

        table = pd.DataFrame(data)
        res = gd.set_with_dataframe(sheet, table, include_column_header=False, row=len(sheet.col_values(col)) + 1,
                                    col=col, include_index=False, resize=False, allow_formulas=True,
                                    string_escaping="default")


class GUI:
    chromedriver_options = None

    @Gooey(
        program_name="Podio Integration tool",
        program_description="This tool is used to scrape Podio updates and moves them into other services",
        terminal_font_color='black',
        terminal_panel_color='white',
        progress_regex=r"^progress: (\d+)/(\d+)$",
        progress_expr="x[0] / x[1] * 100",
        disable_progress_bar_animation=False,
        default_size=(910, 720),
        timing_options={'show_time_remaining': True, 'hide_time_remaining_on_complete': False},
        tabbed_groups=True
    )
    def login_card(self, parser):
        user = login_default['Update Admins']
        log_det = parser.add_argument_group("Login details")

        log_det.add_argument("--username_podio", metavar='Username Podio', default=user['username_podio'])
        log_det.add_argument("--password_podio", metavar='Password Podio', widget='PasswordField',
                            default=user['password_podio'])

        log_det.add_argument("--username_admin", metavar='Username Admin', default=user['username_admin'])
        log_det.add_argument("--password_admin", metavar='Password Admin', widget='PasswordField',
                            default=user['password_admin'])

        log_det.add_argument("--username_pc", metavar='Username Product Service', default=user['username_pc'])
        log_det.add_argument("--password_pc", metavar='Password Product Service', widget='PasswordField',
                            default=user['password_pc'])

        log_det.add_argument("--username_pams", metavar='Username Partner Management System',
                            default=user['username_pams'])
        log_det.add_argument("--password_pams", metavar='Password Partner Management System', widget='PasswordField',
                            default=user['password_pams'])

    def api_keys_card(self, parser):
        user = login_default['Update Admins']
        api_det = parser.add_argument_group("Podio Api Keys")

        api_det.add_argument("--client_id1", metavar='Client ID Podio', default=user['client_id_podio1'])
        api_det.add_argument("--client_secret1", metavar='Client Secret Podio', widget='PasswordField',
                            default=user['client_secret_podio1'])

        api_det.add_argument("--client_id2", metavar='Client ID Podio', default=user['client_id_podio2'])
        api_det.add_argument("--client_secret2", metavar='Client Secret Podio', widget='PasswordField',
                            default=user['client_secret_podio2'])

        api_det.add_argument("--client_id3", metavar='Client ID Podio', default=user['client_id_podio3'])
        api_det.add_argument("--client_secret3", metavar='Client Secret Podio', widget='PasswordField',
                            default=user['client_secret_podio3'])

        api_det.add_argument("--client_id4", metavar='Client ID Podio', default=user['client_id_podio4'])
        api_det.add_argument("--client_secret4", metavar='Client Secret Podio', widget='PasswordField',
                            default=user['client_secret_podio4'])

        api_det.add_argument("--client_id5", metavar='Client ID Podio', default=user['client_id_podio5'])
        api_det.add_argument("--client_secret5", metavar='Client Secret Podio', widget='PasswordField',
                            default=user['client_secret_podio5'])

    def options_card(self, parser):
        gen_opt = parser.add_argument_group("General options")

        gen_opt.add_argument("--threads_num", metavar=" How many threads do you need?", widget="Slider",
                            gooey_options={'min': 1, 'max': 6}, type=int)
        gen_opt.add_argument("--comment_period", metavar=" After [X] days I should add the same comment?",
                            widget="Slider", default=4, gooey_options={'min': 1, 'max': 10}, type=int)

        gen_opt.add_argument("--headless_website", metavar=" ", widget="BlockCheckbox",
                                default=True, action='store_false', gooey_options=
                                {'checkbox_label': " headless website", 'show_label': True})
        gen_opt.add_argument("--All_tasks", metavar=" ", widget="BlockCheckbox",
                                default=True, action='store_false', gooey_options=
                                {'checkbox_label': " All tasks except 'Add commission'", 'show_label': True})

    def tasks_options_card(self, parser, tasks):
        # Dynamic tick boxes to choose tasks that need to be done
        checkboxes = parser.add_argument_group("Detailed tasks")

        for task_key in tasks.keys():
            checkboxes.add_argument(f"--{task_key.replace(' ', '_')}", metavar=' ', widget="BlockCheckbox",
                                    default=False, action='store_true', gooey_options={
                                                                    'checkbox_label': f" {task_key.replace(' ', '_')}",
                                                                    'show_label': True})

    def handle(self):
        tasks = json.load(open("Podio & PAMS fields/Tasks.json"))

        parser = GooeyParser()
        self.options_card(parser)
        self.tasks_options_card(parser, tasks)
        self.login_card(parser)
        self.api_keys_card(parser)

        user_inputs = vars(parser.parse_args())

        # Get only tasks that were checked
        if user_inputs['All_tasks']:  # if All tasks option was blank
            tasks_dict = {
                task_key.replace("_", " "): tasks[task_key.replace("_", " ")]
                for task_key, value in user_inputs.items()
                if task_key.replace("_", " ") in tasks and value
            }
        else:  # If All tasks option was clicked
            tasks_dict = tasks
            tasks_dict.pop("Add commission", None)  # This task can't be run with headless option

        login.update(user_inputs)

        self.setup_chromedriver_options(user_inputs)
        self.threads(user_inputs, tasks_dict)

    def setup_chromedriver_options(self, user_inputs: dict):
        self.chromedriver_options = webdriver.ChromeOptions()

        self.chromedriver_options.add_argument("--disable-extensions")
        self.chromedriver_options.add_argument("--window-size=1920,1080")
        self.chromedriver_options.add_argument("--disable-gpu")
        self.chromedriver_options.add_argument("enable-automation")
        self.chromedriver_options.add_argument("--no-sandbox")
        self.chromedriver_options.add_argument("--dns-prefetch-disable")
        self.chromedriver_options.page_load_strategy = "none"

        prefs = {"profile.default_content_settings.popups": 2, "download.default_directory": os.getcwd()}
        self.chromedriver_options.add_experimental_option("prefs", prefs)

        if not user_inputs["headless_website"] and not user_inputs["Add_commission"]:
            self.chromedriver_options.add_argument("--headless")

    def threads(self, user_inputs: dict, tasks_dict: dict):
        threads_num = user_inputs['threads_num']
        comment_period = user_inputs['comment_period']

        # Collect tasks before update
        access_tokens = [Podio({}, []).__get_access_token__(user_inputs[f'client_id{i}'], user_inputs[f'client_secret{i}'])
                         for i in random.sample(range(1, 6), 5)]
        tasks_list = Podio({}, access_tokens).get_tasks(tasks_dict)

        # Give different tasks between all threads
        threads = []
        l = 0
        for index in range(threads_num):
            start_index = l
            l += int(len(tasks_list) / threads_num)

            end_index = len(tasks_list) if index == threads_num - 1 else l
            end_index = min(end_index, len(tasks_list))

            chrome_service1 = ChromeService(ChromeDriverManager().install())
            # chrome_service1.creationflags = CREATE_NO_WINDOW
            website1 = webdriver.Chrome(options=self.chromedriver_options, service=chrome_service1)
            x = threading.Thread(target=main, args=(website1, tasks_list[start_index:end_index], comment_period,
                                                    tasks_dict, access_tokens))
            threads.append(x)
            x.start()

        for thread in threads:
            thread.join()


if __name__ == "__main__":
    gui = GUI()
    gui.handle()
