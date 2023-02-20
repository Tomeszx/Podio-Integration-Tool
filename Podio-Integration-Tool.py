#!venv/bin/python3.9
import json
import os
import re
import threading
import time
import gspread
import pycountry

import gspread_dataframe as gd
import numpy as np
import pandas as pd

from datetime import datetime
from gooey import Gooey, GooeyParser
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from oauth2client.service_account import ServiceAccountCredentials
from test_podio_data import test_data

select_fields_names = json.load(open("select_fields_names.json"))
input_fields_names = json.load(open("input_fields_names.json"))
tickbox_class_names = json.load(open("tickbox_class_names.json"))
vat_zones = pd.read_csv('vat_zones.csv', index_col=0)
login_default = json.load(open("config.json"))
login = {}


def main(tasks_list: dict, comment_period: int, website) -> None:
    Podio().login(website)
    task_window = website.current_window_handle

    for task_row in tasks_list:
        dict_html = {"task": task_row[0], "part_title": task_row[1], "tasks_keys": task_row[2],
                     "link_to_task": task_row[3], "link_to_shop": task_row[4], "Partner_Name": task_row[5],
                     "partner_type": task_row[4].split("/")[6], 'comment_period': comment_period}

        if "vintage" in dict_html['partner_type']:
            dict_html['partner_type'] = "partners"

        print("\n>>>>", dict_html['Partner_Name'], ">>>>", dict_html['task'], "\n")

        comment, dict_html = Podio().prepare_data(website, task_window, dict_html)
        if (comment is False or "Username" in comment) and "Create core" in dict_html['task']:
            action, comment = Podio().add_username_password(website, dict_html)
            if "Issue" in action:
                Podio().add_error_comment(website, comment, dict_html)
                continue
        elif comment is not False and "go to next task" in comment:
            continue
        elif comment is not False:
            Podio().add_error_comment(website, comment, dict_html)
            continue

        website.execute_script("window.open()")
        website.switch_to.window(website.window_handles[3])

        # Choosing task
        if 'pc location' in dict_html['task'].lower():
            ProductService().create_pc_location(website, dict_html)
            action, comment = ProductService().add_aliases(website, dict_html)

        elif 'add aliases' in dict_html['task'].lower():
            action, comment = ProductService().add_aliases(website, dict_html)

        # Update Admins
        else:
            action, comment = admin_tasks(website, dict_html)

        # Update Podio with comment and click tickbox if needed
        if "Issue" in action or "error" in comment:
            print(Podio().add_error_comment(website, comment, dict_html))
            if action == "Issue, but click tickbox":
                Podio().complete_task(website)
        elif action == "Success":
            Podio().complete_task(website)
            Podio().add_comment(website, comment, dict_html)
        else:
            raise ValueError("Undefined action happened.")


def admin_tasks(website, dict_html: dict) -> (str, str):
    # Check and exclude markets that need to be added
    if "other markets" in dict_html['task'].lower() or "create core" in dict_html['task'].lower():
        all_shop_ids = ""
        for i in dict_html['Markets_to_activate_for_the_partner']:
            if i + "-" not in dict_html['All_Shop_IDs']:
                i = i.replace("SHWRM", "PL")
                all_shop_ids += f',{i}-0' if len(all_shop_ids) > 0 else f'{i}-0'

        if all_shop_ids.count("-0") == 0:
            return "Issue, but click tickbox", "There are no new markets to add for this Partner."

    else:
        all_shop_ids = dict_html['All_Shop_IDs']

    # Update information in all markets one by one
    for shop_id in all_shop_ids.split(","):
        dict_html['market'] = shop_id.split("-")[0]
        dict_html['id'] = shop_id.split("-")[1]

        if 'Additional shipping locations' in dict_html['task'] or 'Return address' in dict_html['task']:
            if dict_html['market'] == "CN":
                continue

            action, comment = Admin().update_extra_shipp_address(website, dict_html)

        elif "commission" in dict_html['task'].lower().replace(" ", ""):
            if dict_html['market'] == "CN":
                continue
            if dict_html.get('commission_values') is None:
                dict_html['commission_values'] = []
            action, comment = Admin().update_commission(website, dict_html)

        elif "IBAN" in dict_html['task'] or "other markets" in dict_html['task'].lower() \
                or "create core" in dict_html['task'].lower() or "all fields" in dict_html['task']:

            dict_html['payment_method'], m = "IBAN/Swift", dict_html['market']
            if "Multiple IBANs" in dict_html:
                if dict_html.get(f"IBAN {m}") and dict_html.get(f"SWIFT {m}"):
                    dict_html['Bank_Account_Number_-_IBAN_(format:_PL123456789)'] = dict_html[f"IBAN {m}"]
                    dict_html['Bank_Account_Number_-_SWIFT'] = dict_html[f"SWIFT {m}"]
                elif dict_html.get(f"Account {m}") and dict_html.get(f"CODE {m}"):
                    dict_html['Bank_Account_Number_-_IBAN_(format:_PL123456789)'] = dict_html[f"Account {m}"]
                    dict_html['Bank_Account_Number_-_SWIFT'] = dict_html[f"CODE {m}"]
                    dict_html['payment_method'] = "Bank transfer"
                else:
                    comment = f"The wrong format, probably missing market in IBAN/SWIFT. " \
                              f"\nCheck if [{dict_html['market']}] is included in the field."
                    return "Issue", comment

            action, comment = Admin().update_edit_view_admin(website, dict_html)
            if "Create core" in dict_html['task'] and shop_id == all_shop_ids.split(",")[-1]:
                Podio().sort_shop_ids(website, dict_html)
        else:
            action, comment = Admin().update_edit_view_admin(website, dict_html)

        if "Issue" in action or "error" in comment:
            return action, comment

    return action, comment


class Podio:
    def login(self, website) -> None:
        website.get("https://podio.com/tasks")
        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.ID, "loginForm")))

        website.find_element(By.XPATH, "//*[@id='email']").send_keys(login['username_podio'])
        website.find_element(By.XPATH, "//*[@id='password']").send_keys(login['password_podio'])
        website.find_element(By.XPATH, "//*[@id='loginFormSignInButton']").click()
        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.ID, "show-more-tasks")))

    def get_tasks(self, website, tasks_keys: dict) -> list:
        self.login(website)
        start_time = time.time()

        # Scroll down to get all tasks
        show_more_tasks = website.find_elements(By.XPATH, '//*[@id="show-more-tasks"]')
        while show_more_tasks:
            website.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            website.execute_script("arguments[0].click();", show_more_tasks[0])
            loaded_elements = len(website.find_elements(By.CLASS_NAME, 'task-wrapper '))
            print(f"Collecting data... {loaded_elements} elements were loaded.")
            time.sleep(1)
            if website.find_elements(By.XPATH, '//*[@id="js-task-list"]/p[1]') or loaded_elements > 1200:
                break

        podio_rows = website.find_elements(By.XPATH, '//*[@class="single-task js-rank-task ui-sortable-handle"]')
        tasks = website.find_elements(By.XPATH, '//*[@class="task-link edit-task-title"]')
        shop_names = website.find_elements(By.XPATH, '//*[@class="linked-item"]')

        # Send all tasks to Sheets (information only)
        all_tasks_podio = [[s.text, t.text, s.get_attribute("href"), t.get_attribute("href")]
                           for t, s in zip(tasks, shop_names)]
        GoogleSheet().send_data(col=1, sheet_name="Tasks", data=all_tasks_podio)

        all_titles_text = [i.text for i in podio_rows]
        collected_titles, current_task, tasks_list = [], 0, []

        xpath = './/a[@class="icon-16 icon-16-trash-small js-delete-task tooltip"]'
        for row_elem, task_elem, shop_name_elem in zip(podio_rows, tasks, shop_names):
            delete_task = row_elem.find_element(By.XPATH, xpath)
            title = row_elem.text

            # Remove duplicated tasks
            task = task_elem.text
            if all_titles_text.count(title) - collected_titles.count(title) > 1:
                website.execute_script("arguments[0].click();", delete_task)
                website.find_element(By.XPATH, '//button[@class="button-new primary confirm-button"]').click()
                print(f"\n\nDeleting task: \n[{delete_task.find_element(By.XPATH, '../../../.').text}] \n[{title}]")
                collected_titles.append(title)
                continue

            # searching for specific tasks
            task_founded = False
            for part_title in tasks_keys:
                if part_title.lower().replace(" ", "") not in task.lower().replace(" ", ""):
                    continue
                if part_title == "commission" and "add " in task.lower():
                    continue
                task_founded = True
                break

            if task_founded:
                link_to_task = task_elem.get_attribute("href")
                link_to_shop = shop_name_elem.get_attribute("href")

                tasks_list.append([task, part_title, tasks_keys, link_to_task, link_to_shop, shop_name_elem.text])

        print(f"\n\nJust finished collecting data. time spent on this:",
              f"{round((time.time() - start_time) / 60, 2)} min.",
              f"\n There are: {len(tasks_list)} tasks in Podio\n")

        return tasks_list

    def get_fields_dict(self, website, task_dict: dict):
        podio_data = {}
        all_names = website.find_elements(By.TAG_NAME, 'li')
        for i in all_names:
            key = i.find_elements(By.XPATH, ".//div[@class='label-content']")
            if key and key[0].text.replace("* ", "").replace(" ", "_") in task_dict:
                child_text_input = i.find_elements(By.XPATH, './/p')
                child_email_input = i.find_elements(By.XPATH, './/div[contains(text(), "@")]')
                child_type_box = i.find_elements(By.XPATH, './/li')
                child_select_box = i.find_elements(By.XPATH, './/select')
                child_calc_box = i.find_elements(By.XPATH, './/div[@class="help-text-trigger"]')
                child_number_input = i.find_elements(By.XPATH, './/div[@class="number-wrapper"]')
                child_date_input = i.find_elements(By.XPATH, './/div[@class="field-date-display"]')
                child_phone_input = i.find_elements(By.XPATH, './/div[@class="phone-field-component__view-mode__cell"]')

                key = key[0].text.replace("* ", "").replace(" ", "_")

                if child_text_input:
                    podio_data[key] = " ".join(i.text for i in child_text_input)
                elif child_email_input:
                    podio_data[key] = [i.text for i in child_email_input][:5]
                elif child_type_box:
                    podio_data[key] = [i.text for i in child_type_box if "selected" in i.get_attribute('class')]
                elif child_select_box:
                    podio_data[key] = Select(child_select_box[0]).first_selected_option.text
                elif child_calc_box:
                    podio_data[key] = child_calc_box[0].text
                elif child_number_input:
                    podio_data[key] = child_number_input[0].text
                elif child_phone_input:
                    index = len(child_phone_input) // 3
                    podio_data[key] = child_phone_input[index].text
                elif child_date_input and child_date_input[0].text != "":
                    podio_data[key] = datetime.strptime(' '.join(child_date_input[0].text.split('\n')[1:3]), "%d %B %Y")

        return podio_data

    def prepare_data(self, website, task_window, dict_html: dict) -> (str, dict):
        task_dict = dict_html['tasks_keys'][dict_html['part_title']]

        # Close all unnessesary windows
        while len(website.window_handles) > 1:
            window_handle = website.window_handles[len(website.window_handles) - 1]
            website.switch_to.window(window_handle)
            if window_handle != task_window:
                try:
                    website.execute_script("window.close()")
                except Exception:
                    continue
        website.switch_to.window(task_window)

        website.execute_script("window.open()")
        website.switch_to.window(website.window_handles[1])
        website.get(dict_html['link_to_task'])
        WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.ID, "task-permalink")))

        task_requester = website.find_elements(By.XPATH, '//*[@id="task-permalink"]/div/div[2]/div[3]/div[2]/p')
        if task_requester and "details" not in task_requester[0].text:
            dict_html['task_requester'] = task_requester[0].text
        else:
            dict_html['task_requester'] = False

        website.execute_script("window.open()")
        website.switch_to.window(website.window_handles[2])
        website.get(dict_html['link_to_shop'])

        # Wait for the information on the page
        WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "frame-label")))
        if website.find_elements(By.XPATH, "/html/body/center[1]/h1"):
            website.refresh()
            WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "frame-label")))

        # if we haven't got all_shop_ids then go to next task
        if "-" not in website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[2]/div').text and \
                'core' not in dict_html['task'].lower():
            return "Issue go to next task", dict_html

        # Get dict with all needed information from Podio
        podio_data = self.get_fields_dict(website, task_dict)

        # Test the data (that all elements in the dict are in the correct format)
        comment, new_id, error = test_data(podio_data, task_dict, dict_html)
        print(comment) if comment else print("The data looks good!")

        # If there is an issue with formatting then send comment to Podio and go to next task
        if "wrong format" in error:
            if "There are no new shops to create." in comment:
                self.complete_task(website)
            return comment, dict_html | podio_data
        return comment, dict_html | podio_data

    def add_username_password(self, website, dict_html: dict) -> (str, str):
        files = website.find_elements(By.XPATH, '//h5[@class="file-field-item-component__title"]')
        pdf_contract = [True for i in files if ".pdf" in i.find_element(By.XPATH, './/a').get_attribute("title")]
        if not pdf_contract:
            return "Issue", "error: Can`t create admins because PDF contract is not attched to the Podio."

        fields = [["username-2" if "brands" in dict_html['partner_type'] else "username", dict_html['Username']],
                  ['password', dict_html['Password']]]

        for field in fields:
            line = website.find_element(By.XPATH, f'//*[@id="{field[0]}"]/div[1]/div[2]/div')

            line.click()

            input_f = website.find_element(By.XPATH, f'//*[@id="{field[0]}"]/div[1]/div[2]/div/input')
            input_f.clear()
            input_f.send_keys(field[1])

            website.find_element(By.XPATH, f'//*[@id="{field[0]}"]/div[1]/div[1]/div/div[2]').click()

        return "", ""

    def add_new_shop_id(self, website, new_id: str) -> None:
        website.switch_to.window(website.window_handles[2])

        all_id_field = website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[2]/div')
        ids_before = all_id_field.text if "Add" not in all_id_field.text else ""
        shop_ids = f"{ids_before},{new_id}" if ("Add" not in all_id_field.text or all_id_field.text == "") else new_id
        all_id_field.click()

        all_id_input = website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[2]/div/input')
        all_id_input.clear()
        all_id_input.send_keys(shop_ids)

        website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[1]/div/div[2]').click()
        time.sleep(0.5)

    def sort_shop_ids(self, website, dict_html: dict) -> str:
        website.switch_to.window(website.window_handles[2])

        all_id_field = website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[2]/div')
        markets = [i.split("-")[0] for i in all_id_field.text.split(",")]
        ids = all_id_field.text.split(",")
        all_id_field.click()

        all_id_input = website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[2]/div/input')
        all_id_input.clear()

        home_market = dict_html['Home_Market']
        if home_market.upper() in {'DK', 'SE', 'NL', 'BE', 'PL', 'CH', 'NO'} and home_market.upper() in markets:
            ids.insert(0, ids.pop(ids.index(*[x for x in ids if re.search(home_market, x)])))
        elif "NL" in markets:
            ids.insert(0, ids.pop(ids.index(*[x for x in ids if re.search('NL', x)])))
        else:
            core_priority = [i for i in ["DK", "BE", "NO", "SE"] if i in markets]
            ids.insert(0, ids.pop(ids.index(*[x for x in ids if re.search(core_priority[0], x)])))

        all_id_input.send_keys(f"{','.join(ids)}")

        website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[1]/div/div[2]').click()
        time.sleep(0.5)

        return all_id_field.text

    def complete_task(self, website) -> bool:
        # click on the tasks tick box
        website.switch_to.window(website.window_handles[1])
        website.refresh()

        xpath = '//*[@id="task-permalink"]/div/div[1]/div[1]/div[1]/span/span/img'
        box = WebDriverWait(website, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        box.click()

        box_status = website.find_element(By.XPATH, '//*[@id="task-permalink"]/div/div[1]/div[1]/div[1]/span')

        return "checked" in box_status.get_attribute("class")

    def add_comment(self, website, comment: str, dict_html: dict) -> str:
        website.switch_to.window(website.window_handles[2])

        website.refresh()
        loops = 0
        while not website.find_elements(By.XPATH, '//textarea'):
            loops += 1
            time.sleep(0.5)
            website.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            if loops == 11:
                raise TimeoutError("Can't find textarea")

        text_box = website.find_element(By.XPATH, '//textarea[@placeholder="Add a comment"]')
        text_box.click()
        try:
            if dict_html['task_requester'] is False or "Update Admins" in dict_html['task_requester']:
                raise ValueError("Empty requester.")

            xpath = f'//span[contains(@class, "value")]/b[contains(text(), "{dict_html["task_requester"]}")]'
            x = [[text_box.send_keys(i), time.sleep(0.1)] for i in f"@{dict_html['task_requester']}"]
            user = WebDriverWait(website, 6).until(EC.presence_of_element_located((By.XPATH, xpath)))
            user_id = user.find_element(By.XPATH, "./../../../../..").get_attribute("data-id")
            msg = f"@[{dict_html['task_requester']}](user:{user_id})\n\n{comment}"
        except Exception:
            msg = comment

        text_box.clear()
        time.sleep(1)
        text_box.send_keys(msg)

        button = WebDriverWait(website, 10).until(EC.element_to_be_clickable((By.XPATH, '//button[@label="Add"]')))
        button.click()
        time.sleep(1)

        table = pd.DataFrame([[dict_html["Partner_Name"], dict_html['task'], comment, dict_html["link_to_shop"],
                               datetime.now()]])
        GoogleSheet().send_data(col=1, sheet_name="Bot msgs", data=table)

        website.refresh()
        WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.XPATH, '//*[@class="content bd"]')))

        return website.find_elements(By.XPATH, '//*[@class="content bd"]')[-1].text

    def add_error_comment(self, website, comment: str, dict_html: dict) -> str:
        website.switch_to.window(website.window_handles[2])
        check = re.sub('[^a-zA-Z0-9]', '', comment).lower()

        # Check if adding the comment is needed
        while True:
            try:
                dupl_com = True
                website.find_element(By.XPATH, '//li[@data-type="comment"]').click()
                WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.XPATH, '//div[@class="author"]')))
                time.sleep(1)

                msgs = website.find_elements(By.XPATH, '//div[@class="activity-group"]')
                for msg in msgs:
                    comm_date = msg.find_element(By.XPATH, './/time')
                    comm_date = datetime.strptime(comm_date.get_attribute('datetime').split(" ")[0], "%Y-%m-%d").date()

                    author = msg.find_element(By.XPATH, './/div[@class="author"]').text

                    text = re.sub('[^a-zA-Z0-9]', '', msg.text).lower()

                    if (
                            "Update Admins" in author
                            and (datetime.now().date() - comm_date).days < dict_html['comment_period']
                            and text != ""
                            and check in text
                    ):
                        dupl_com = 'Comment not added. (Duplicate).'
                        print(dupl_com)
                        break
            except Exception:
                website.refresh()
                time.sleep(2)
                website.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                continue
            break

        if dupl_com != "Comment not added. (Duplicate).":
            return self.add_comment(website, comment, dict_html)
        else:
            return dupl_com


class Admin:
    def __init__(self):
        self.vat_rate = {'SE': 25, 'DE': 19, 'DK': 25, 'BE': 21, 'PL': 23, "SHWRM": 23, 'NL': 21, 'IT': 22,
                         'ES': 21, 'FR': 20, 'FI': 24, 'NO': 25, 'UK': 20, 'CH': 7.7}
        self.addi_shipping_fields = ['zipcode', 'name', 'street', 'street2', 'city']

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

    def get_edit_view_values(self, website) -> dict:
        tickbox_dict = {
            i.get_attribute("class"): 'ON' if i.is_selected() else "OFF"
            for i in website.find_elements(By.TAG_NAME, "input")
        }
        input_dict = {
            name: website.find_element(By.XPATH, f'//*[@{"class" if "feature" in name else "name"}="{name}"]').
            get_attribute("value")
            for name in input_fields_names.values()
        }
        select_dict = {
            name: Select(website.find_element(By.XPATH, f'//*[@name="{name}"]')).first_selected_option.text
            for name in select_fields_names.values()
        }

        return tickbox_dict | input_dict | select_dict

    def fill_tickbox(self, website, dict_html: dict) -> None:
        for key in tickbox_class_names:
            if key not in dict_html:
                continue
            time.sleep(0.1)

            element = website.find_element(By.CLASS_NAME, tickbox_class_names[key])
            if dict_html[key] and dict_html[key] != 0 and not element.is_selected():
                element.click()
            elif (not dict_html[key] or dict_html[key] == 0) and element.is_selected():
                element.click()

    def fill_select_fields(self, website, dict_html: dict) -> (str, str):
        for key in select_fields_names:
            if key not in dict_html:
                continue
            time.sleep(0.1)

            element = Select(website.find_element(By.NAME, select_fields_names[key]))
            try:
                element.select_by_visible_text(dict_html[key])
            except NoSuchElementException as e:
                if "payment_method" in key:
                    return "Issue", f"The account number was not updated on [{dict_html['market']}] market, " \
                                    f"due to the lack of 'account number' option in the admin. Please provide " \
                                    f"the IBAN & SWIFT number instead."
                elif 'country' in key.lower() and dict_html[key] not in [i.text for i in element.options]:
                    return "Issue", f"Can`t find the country [{dict_html[key]}] on the Admin`s [{dict_html['market']}]"\
                                    f" market. The field [{key}] cause an issue." \
                                    f" Please make sure that the country field has correct country."
                elif 'country' in key.lower():
                    element.select_by_value("Netherlands")
                else:
                    raise ValueError("There is some issue with select fields.") from e

        return "Ok", "Ok"

    def fill_input_fields(self, website, dict_html: dict) -> None:
        for key in input_fields_names:
            if key not in dict_html or not dict_html[key]:
                continue
            time.sleep(0.1)

            method = "class" if "feature" in input_fields_names[key] else "name"
            element = website.find_element(By.XPATH, f'//input[@{method}="{input_fields_names[key]}"]')

            if not element.is_displayed():
                print(f"This element is not displayed on the page: {input_fields_names[key]}.")
                continue

            try:
                if key == "Date_of_signing":
                    signup_date = [element.send_keys(i) for i in reversed(str(dict_html[key]).split(" ")[0].split("-"))]
                elif key == "Shop_Name" and dict_html['market'] == "CN":
                    element.clear()
                    element.send_keys(f"{dict_html[key]} by Miinto")
                else:
                    element.clear()
                    element.send_keys(dict_html[key])
            except:
                print(key, "->>>><<<<< this fields has the issue.")
                raise ValueError

    def fill_new_market_fields(self, website, dict_html: dict) -> None:
        website.find_element(By.XPATH, '//input[@name="password"]').send_keys(dict_html["Password"])
        website.find_element(By.XPATH, '//input[@name="password2"]').send_keys(dict_html["Password"])

        vat_zone = Select(website.find_element(By.XPATH, '//select[@name="vat_zone"]'))
        if dict_html['Home_Market'] == 'UK':
            vat_zone.select_by_visible_text('foreign')
        else:
            search_vat_zone = vat_zones.get(dict_html['Home_Market'])
            v_z_value = search_vat_zone[dict_html['market']] if search_vat_zone is not None else 'eu'
            vat_zone.select_by_visible_text(v_z_value)

    def update_edit_view_admin(self, website, dict_html: dict) -> (str, str):
        try:
            self.open(website, dict_html['market'], dict_html['id'])
        except Exception:
            return "Issue", "There is an issue in All-shop-IDS or related field."

        if dict_html['market'] == dict_html['All_Shop_IDs'].split(",")[-1].split("-")[0]:
            fields_before = self.get_edit_view_values(website)

        self.fill_tickbox(website, dict_html)
        action, comment = self.fill_select_fields(website, dict_html)
        self.fill_input_fields(website, dict_html)

        if "Issue" in action:
            return action, comment
        elif 'Create core' in dict_html['task'] or 'other markets' in dict_html['task'].lower():
            self.fill_new_market_fields(website, dict_html)

        response = self.save_edit_view(website, dict_html)
        if "error" in response:
            return "Issue", response
        elif "other market" in dict_html['task'].lower() or "Create core" in dict_html['task']:
            fields_before = {}
        elif dict_html['market'] != dict_html['All_Shop_IDs'].split(",")[-1].split("-")[0]:
            return "Success", "Simple comment. (waiting for last market to generate appropriate comment)."

        fields_after = self.get_edit_view_values(website)
        all_f = {**tickbox_class_names, **input_fields_names, **select_fields_names}
        updated_fields = "\n\n".join(f"{i.replace('_', ' ')}:\n---\n\n >[{fields_before.get(all_f[i])}]-->"
                                     f"[{fields_after[all_f[i]]}]" for i in all_f if i in dict_html).replace("None", "")

        return "Success", f"Successfully finished task: [{dict_html['task']}].\n" \
                          f"What was updated?\n\n---\n" + updated_fields

    def save_edit_view(self, website, dict_html: dict) -> str:
        save_button = website.find_element(By.XPATH, '//button[@class="btn btn-success"]')
        website.execute_script("arguments[0].click();", save_button)

        # Get save result
        time_start_while = time.time()
        success_fields, error_fields = [], []
        while not success_fields and not error_fields and time.time() - time_start_while < 4:
            success_fields = website.find_elements(By.XPATH, '//*[@class="alert alert-success alert--success"]')
            error_fields = website.find_elements(By.XPATH, '//*[@class="alert alert-error alert--error"]')

        if success_fields:
            response = "\n".join([i.text for i in success_fields])

        elif error_fields:
            error_message = "\n".join([i.text for i in error_fields])
            response = f"There was an issue with task [{dict_html['task']}].\n\n" \
                       f"(The error refers to Admin not Podio)\n" \
                       f"Previous fields setup in {dict_html['market']} Admin has some errors:\n\n ---\n"
            for line in error_message.split("\n"):
                separator = "".join(i for i in [" cannot be", " must be", " does not", 'Invalid'] if i in line)
                separator = separator or ""
                response += "Incorrect field [" + f"]\n --- \n\n > {separator}".join(line.split(separator)) + "\n\n"
            response += "\n\n --- \nTo handle this error please fill in the related fields in Podio.\n\n --- "
            return response

        else:
            response = f"\n\nThere was an connection error on the page. Please check if the " \
                       f"Admin was created on [{dict_html['market']}] market."
            if "other market" in dict_html['task'].lower() or "Create core" in dict_html['task']:
                return response

            self.update_edit_view_admin(website, dict_html)
            return "Try Again"

            # Update Podio with new market
        if "other markets" in dict_html['task'].lower() or "Create core" in dict_html['task']:
            new_id = dict_html['market'] + '-' + re.findall(r'\d{4}', website.current_url)[0]
            print("The new id is:", new_id)
            Podio().add_new_shop_id(website, new_id)
            website.switch_to.window(website.window_handles[3])

        return response

    def get_shipp_address_values(self, website) -> str:
        titles = ["Address type", "Name", "Street", "Street 2", "Postcode", "City", "Country", "Action(s)"]

        rows = [[s.text for s in i.find_elements(By.XPATH, './/td')] for i in
                website.find_elements(By.XPATH, "//tr")[1:]]

        r = []
        for n, x in enumerate(rows, 1):
            x = f"{rows[n - 1][0]} {n}\n---\n{''.join([f'|{titles[i]}: [{x[i]}]' for i, _ in enumerate(rows[0][1:7], 1)])}"
            r.append(x)

        return "\n\n".join(r).replace("|", f"\n >").replace(" address", "")

    def update_extra_shipp_address(self, website, dict_html: dict) -> (str, str):
        url, sec_part = self.open(website, dict_html['market'], dict_html['id'])

        website.get(url + f"admin/action/_login.php?login_as={dict_html['id']}")
        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'row-fluid')))

        website.get(url + 'admin/shop-addresses.php')
        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.NAME, 'shop_street2')))

        # DELETE EXISTING ADDRESSES
        links = [i.find_element(By.XPATH, '../.').get_attribute("href") for i in
                 website.find_elements(By.XPATH, '//button[@class="btn btn-mini"]')
                 if i.find_element(By.XPATH, '../.').get_attribute("href")]

        for link in links:
            website.get(link)
            xpath = '//button[@class="btn btn-danger address-delete"]'
            delete = WebDriverWait(website, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            delete.click()

            acc = WebDriverWait(website, 10).until(EC.element_to_be_clickable((By.XPATH, '//button[@class="confirm"]')))
            time.sleep(1)
            acc.click()

            WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH,
                                                                             '//div[contains(@class, "alert alert")]')))
        # ADD NEW ADDRESSES
        for address_num in dict_html["shipping_locations"]:
            address_dict = dict_html["shipping_locations"][address_num]

            website.get(url + 'admin/shop-addresses.php?method=getAddressCreateForm')

            xpath = '//select[@name="address_type_id"]'
            WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, xpath)))
            address_type = Select(website.find_element(By.XPATH, xpath))
            address_type.select_by_value("1") if "sender" in address_num.lower() else address_type.select_by_value("2")

            for input_name in self.addi_shipping_fields:
                field = website.find_element(By.XPATH, f'//input[@name="{input_name}"]')
                field.clear()
                field.send_keys(address_dict[input_name])

            country = Select(website.find_element(By.XPATH, '//select[@name="country_code"]'))
            country.select_by_value(address_dict['countrycode'])
            time.sleep(0.5)

            website.find_element(By.XPATH, '//button[@type="submit"]').click()
            xpath = '//div[contains(@class, "alert alert")]'
            WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, xpath)))

        values = self.get_shipp_address_values(website)
        website.get(url + 'admin/action/_login.php?todo=admin_re_login')
        time.sleep(1)

        return "Success", f"Successfully finished adding the additional shipping locations to Admin.\n" \
                          f"What was updated?\n\n---\n" + values

    def update_commission(self, website, dict_html: dict) -> (str, str):
        # sourcery skip: identity-comprehension
        partner_type_box = {"partners": ["Name: Shop", "Store-"], "brands": ["Name: Brand", "Brand-"]}
        url, sec_part = self.open(website, dict_html['market'], dict_html['id'])

        pure_comm = dict_html['Pure_commission_to_be_charged_on_balanced_orders']
        new_comm = round(float(pure_comm) * ((self.vat_rate[dict_html['market']] / 100) + 1), 2)

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
        drag = [i for i in website.find_elements(By.XPATH, f"//li[contains(@data-default-block-type, '"
                                                           f"{partner_type_box['partners'][1]}')]")][0]

        xpath = '//div[@class="commission-tools__block js-rules-list"]'
        try:
            drop = [i for i in website.find_elements(By.XPATH, xpath) if partner_type_box[
                dict_html['partner_type']][0].lower().replace(" ", "") in i.text.lower().replace(" ", "")][0]
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

                    if shop.get_attribute('id').split("-")[-1] == dict_html['id']:
                        break

                close_edit = website.find_element(By.XPATH, '//*[@id="ruleForm"]/div/input[2]').click()

            else:
                if not all_shops or shop.get_attribute('id').split("-")[-1] != dict_html['id']:
                    raise ValueError(f"Can`t find shop id in commission tool - market [{dict_html['market']}]")

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
            shop = [i for i in all_shops if i.get_attribute('id').split("-")[-1] == dict_html['id']][0]
            shop.click()

        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, '//*[@id="ruleForm"]/input[1]')))
        name = website.find_element(By.XPATH, '//*[@id="ruleForm"]/input[1]')
        name.clear()
        name.send_keys(dict_html['Shop_Name'])

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
                reducer_type = "min"
            elif max(all_d_comm) == float(default_commission.split(" ")[0]):
                reducer_type = "max"
        elif float(new_comm) < float(default_commission.replace(' %', '')):
            reducer_type = "min"
        elif float(new_comm) > float(default_commission.replace(' %', '')):
            reducer_type = "max"

        website.switch_to.window(website.window_handles[3])

        reducer_field = Select(website.find_element(By.XPATH, '//select[@name="commission_reducer_type"]'))
        if reducer_field.first_selected_option.get_attribute("value") != reducer_type:
            reducer_field.select_by_value(reducer_type)

            response = self.save_edit_view(website, dict_html)
            if "issue" in response:
                return "Issue", response

        dict_html['commission_values'].append(f" >{dict_html['market']} ({self.vat_rate[dict_html['market']]}%VAT): "
                                              f"[{old_com}%] {prev_reucer}->[{new_comm}%] {reducer_type}\n")

        comment = \
            f"Successfully finished updating commission in Admin.\n" \
            f"What was updated?\n\n---\n" \
            f"\nCommission was changed to\n---\n > [{dict_html['Pure_commission_to_be_charged_on_balanced_orders']}]" \
            f"\n\nCommission value incl. VAT:\n---\n" \
            + "\n\n".join(dict_html['commission_values'])
        return "Success", comment


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

    def create_pc_location(self, website, dict_html: dict) -> (str, str):
        website.switch_to.window(website.window_handles[2])

        if "PC_location_name" in dict_html:
            return "Issue, but click tickbox", "The location is created already"

        primary_id = dict_html["All_Shop_IDs"].split(",")[0].split("-")[1]
        primary_market = dict_html["All_Shop_IDs"].split(",")[0].split("-")[0]

        prefix = "S" if dict_html["partner_type"] == "partners" else "B"
        dict_html["PC_location_name"] = f'{dict_html["Home_Market"]}-{prefix} {dict_html["Shop_Name"]} {primary_id}'

        pc_frame = website.find_element(By.XPATH, '//*[@id="pc-location-name"]/div[1]/div[2]/div/div')
        pc_frame.click()
        iframe = website.find_element(By.XPATH, '//iframe')
        website.switch_to.frame(iframe)

        pc_input = website.find_element(By.XPATH, '//*[@id="tinymce"]/p')
        pc_input.send_keys(dict_html["PC_location_name"])

        website.switch_to.default_content()
        website.find_element(By.XPATH, '//*[@id="pc-location-name"]/div[1]/div[1]/div/div[2]').click()

        website.execute_script("window.open()")
        website.switch_to.window(website.window_handles[4])
        self.open_pc(website)

        website.get('https://proxy-product.miinto.net/location')
        WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, "//h1[text() = 'Create Location']")))

        loc_name = website.find_element(By.XPATH, '//input[@id="locationName"]')
        loc_name.send_keys(dict_html["PC_location_name"])

        unified_loc_id = website.find_element(By.XPATH, '//input[@id="locationUnifiedId"]')
        unified_loc_id.send_keys(f"1-m!i!s-{self.dict_location[primary_market]}-{primary_id}")

        website.find_element(By.XPATH, "/html/body/div[1]/div/main/form/div[2]/span").click()
        country = pycountry.countries.get(alpha_2=primary_market)
        language = pycountry.languages.get(alpha_2=dict_html['Home_Market'])

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

    def add_aliases(self, website, dict_html: dict) -> (str, str):
        website.switch_to.window(website.window_handles[3])
        self.open_pc(website)

        if "PC_location_name" not in dict_html.keys():
            return "Issue", "PC location name is blank or incorrect"

        website.get('https://proxy-product.miinto.net/locations')
        WebDriverWait(website, 10).until(EC.visibility_of_element_located((By.XPATH,
                                                                           "//h1[contains(text(), 'Locations')]")))

        try:
            while dict_html["PC_location_name"] not in website.find_element(By.XPATH, '//tbody').get_attribute(
                    "textContent"):
                next_page = website.find_element(By.XPATH, '//*[@class="feather feather-chevron-right"]').click()
                time.sleep(0.2)
        except Exception:
            comment = "error: Can`t find Pc location name in PC."
            return "Issue", comment

        cells = website.find_elements(By.XPATH, '//tr')
        edit_link = [i.find_element(By.XPATH, './/a[@class="btn btn-outline-primary"]').get_attribute("href")
                     for i in cells if dict_html["PC_location_name"] in i.get_attribute("textContent")][0]

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

                for i, shop_id in enumerate(dict_html["All_Shop_IDs"].split(",")):
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
        creds = ServiceAccountCredentials.from_json_keyfile_name('client_secret.json', scope)
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
        program_name="Agi Bot - Update",
        program_description="Update Admins with Agi Bot!",
        terminal_font_color='black',
        terminal_panel_color='white',
        progress_regex=r"^progress: (\d+)/(\d+)$",
        progress_expr="x[0] / x[1] * 100",
        disable_progress_bar_animation=False,
        default_size=(810, 720),
        timing_options={'show_time_remaining': True, 'hide_time_remaining_on_complete': False}
    )
    def handle(self):
        parser = GooeyParser()

        user = login_default['Update Admins']
        parser.add_argument("--username_podio", metavar='Username Podio', default=user['username_podio'])
        parser.add_argument("--password_podio", metavar='Password Podio', widget='PasswordField',
                            default=user['password_podio'])

        parser.add_argument("--username_admin", metavar='Username Admin', default=user['username_admin'])
        parser.add_argument("--password_admin", metavar='Password Admin', widget='PasswordField',
                            default=user['password_admin'])

        parser.add_argument("--username_pc", metavar='Username Product Service', default=user['username_pc'])
        parser.add_argument("--password_pc", metavar='Password Product Service', widget='PasswordField',
                            default=user['password_pc'])

        parser.add_argument("--threads_num", metavar="How many processes do you need at once?", widget="Slider",
                            default=4, gooey_options={'min': 1, 'max': 6}, type=int)
        parser.add_argument("--comment_period", metavar="After [X] days I should add the same comment?",
                            widget="Slider", default=4, gooey_options={'min': 1, 'max': 10}, type=int)

        checkboxes = parser.add_argument_group('Tasks from Podio', gooey_options={'columns': 1 - 2})
        checkboxes.add_argument("--headless_website", metavar=" ", widget="BlockCheckbox",
                                default=True, action='store_false', gooey_options=
                                {'checkbox_label': "headless website", 'show_label': True})
        checkboxes.add_argument("--All_tasks", metavar=" ", widget="BlockCheckbox",
                                default=True, action='store_false', gooey_options=
                                {'checkbox_label': "All tasks except 'Add commission'", 'show_label': True})

        # Dynamic tick boxes to choose tasks that need to be done
        tasks = json.load(open("Tasks.json"))
        for index, task_key in enumerate(tasks.keys()):
            if index == 0:
                checkboxes = parser.add_argument_group('Detailed tasks', gooey_options={'columns': 1 - 6})
            if index < 4:
                checkboxes.add_argument(f"--{task_key.replace(' ', '_')}", metavar=' ',
                                        widget="BlockCheckbox", default=False, action='store_true',
                                        gooey_options={'checkbox_label': task_key.replace(' ', '_'),
                                                       'show_label': True})
            elif (index / 4).is_integer():
                checkboxes = parser.add_argument_group('', gooey_options={'columns': 1 - 6})
            if index >= 4:
                checkboxes.add_argument(f"--{task_key.replace(' ', '_')}", metavar=' ',
                                        widget="BlockCheckbox", default=False, action='store_true',
                                        gooey_options={'checkbox_label': task_key.replace(' ', '_'),
                                                       'show_label': True})

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

        prefs = {"profile.default_content_settings.popups": 2, "download.default_directory": os.getcwd()}
        self.chromedriver_options.add_experimental_option("prefs", prefs)

        if not user_inputs["headless_website"] and not user_inputs["Add_commission"]:
            self.chromedriver_options.add_argument("--headless")

    def threads(self, user_inputs: dict, tasks_dict: dict):
        threads_num = user_inputs['threads_num']
        comment_period = user_inputs['comment_period']

        os.environ["WDM_LOG_LEVEL"] = "0"
        website = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()),
                                   options=self.chromedriver_options)

        # Collect tasks before update
        tasks_list = Podio().get_tasks(website, tasks_dict)
        np.random.shuffle(tasks_list)
        website.close()

        # Give different tasks between all threads
        threads = []
        l = 0
        for index in range(threads_num):
            start_index = l
            l += int(len(tasks_list) / threads_num)

            if index == threads_num - 1:
                print(index)
                end_index = len(tasks_list)

            else:
                end_index = l

            end_index = min(end_index, len(tasks_list))
            print(start_index, end_index, "thread_num", index)

            chrome_service1 = ChromeService(ChromeDriverManager().install())
            # chrome_service1.creationflags = CREATE_NO_WINDOW
            website1 = webdriver.Chrome(options=self.chromedriver_options, service=chrome_service1)
            x = threading.Thread(target=main, args=(tasks_list[start_index:end_index], comment_period, website1))
            threads.append(x)
            x.start()

        for thread in threads:
            thread.join()


if __name__ == "__main__":
    gui = GUI()
    gui.handle()
