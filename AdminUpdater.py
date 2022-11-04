#!venv/bin/python3.9
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
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from oauth2client.service_account import ServiceAccountCredentials
from test_podio_data import test_data


def g_sheets(col, sheet_name, data):
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
    gd.set_with_dataframe(sheet, table, include_column_header=False, row=len(sheet.col_values(col)) + 1, col=col,
                          include_index=False, resize=False, allow_formulas=True, string_escaping="default")


class Podio_data:
    def login_podio(self, website):
        website.get("https://podio.com/tasks")
        element = WebDriverWait(website, 10).until(EC.presence_of_element_located((By.ID, "loginForm")))

        website.find_element(By.XPATH, "//*[@id='email']").send_keys("XXX")
        website.find_element(By.XPATH, "//*[@id='password']").send_keys("XXX")
        website.find_element(By.XPATH, "//*[@id='loginFormSignInButton']").click()
        website.implicitly_wait(4)
        time.sleep(1)

    def get_tasks(self, website, tasks_keys):
        self.login_podio(website)
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
        g_sheets(col=1, sheet_name="Tasks", data=all_tasks_podio)

        all_titles_text = [i.text for i in podio_rows]
        collected_titles, current_task, tasks_list = [], 0, []

        for row, task, shop_name in zip(podio_rows, tasks, shop_names):
            delete_task = row.find_element(By.XPATH, './/a[@class="icon-16 icon-16-trash-small js-delete-task tooltip"]')
            title = row.text

        # Remove duplicated tasks
            task_text = task.text
            if all_titles_text.count(title) - collected_titles.count(title) > 1:
                website.execute_script("arguments[0].click();", delete_task)
                website.find_element(By.XPATH, '//button[@class="button-new primary confirm-button"]').click()
                print(f"\n\nDeleting task: \n[{delete_task.find_element(By.XPATH, '../../../.').text}] \n[{title}]")
                collected_titles.append(title)
                continue

        # searching for specific tasks
            task_founded = False
            for part_title in tasks_keys.keys():
                if part_title.lower().replace(" ", "") in task_text.lower().replace(" ", ""):
                    if part_title == "commission" and "add " in task_text.lower():
                        continue
                    task_founded = True
                    break

            if task_founded:
                link_to_task = task.get_attribute("href")
                link_to_shop = shop_name.get_attribute("href")

                tasks_list.append([task_text, part_title, tasks_keys, [],
                                   link_to_task, link_to_shop, shop_name.text])
        else:
            print(f"\n\nJust finished collecting data. time spent on this:",
                  f"{round((time.time() - start_time) / 60, 2)} min.",
                  f"\n There are: {len(tasks_list)} tasks in Podio\n")

            return tasks_list

    def get_podio_data(self, tasks_list, website, task_index, end_index, thread_num, comment_period):
        self.login_podio(website)

        task_window = website.current_window_handle
        for task_row in tasks_list:
            start_time = time.time()

        # Close all unnessesary windows
            while len(website.window_handles) > 1:
                window_handle = website.window_handles[len(website.window_handles) - 1]
                website.switch_to.window(window_handle)
                if window_handle != task_window:
                    try:
                        website.execute_script("window.close()")
                    except:
                        continue
            website.switch_to.window(task_window)
            task_index += 1

            task_text, part_title, tasks_keys, dict_html, link_to_task, link_to_shop, shop_name = \
                task_row[0], task_row[1], task_row[2], task_row[3], task_row[4], task_row[5], task_row[6]

            print("\n>>>>", shop_name, ">>>>", task_text, "\n",
                  f"Progress: {task_index}/{end_index}".center(50), "thread_num", thread_num + 1)
            task_dict = tasks_keys[part_title]

            website.execute_script("window.open()")
            website.switch_to.window(website.window_handles[1])
            website.get(link_to_task)
            task_requester = website.find_elements(By.XPATH, '//*[@id="task-permalink"]/div/div[2]/div[3]/div[2]/p')

            if "details" not in task_requester[0].text:
                dict_html = {'task_requester': task_requester[0].text}
            else:
                dict_html = {'task_requester': False}

            website.execute_script("window.open()")
            website.switch_to.window(website.window_handles[2])
            website.get(link_to_shop)

        # Wait for the information on the page
            while not website.find_elements(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[2]/div'):
                time.sleep(0.5)
                if website.find_elements(By.XPATH, "/html/body/center[1]/h1"):
                    website.refresh()
                    time.sleep(2)

        # if we haven't got all_shop_ids then go to next task
            if "-" not in website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[2]/div').text:
                continue

        # Get dict with all needed information from Podio
            all_names = website.find_elements(By.TAG_NAME, 'li')
            for i in all_names:
                website.implicitly_wait(0)
                key = i.find_elements(By.XPATH, ".//div[@class='label-content']")
                if key and key[0].text.replace("* ", "").replace(" ", "_") in task_dict:
                    child_text_input = i.find_elements(By.XPATH, './/p')
                    child_email_input = i.find_elements(By.XPATH, './/div[contains(text(), "@")]')
                    child_type_box = i.find_elements(By.XPATH, './/li')
                    child_select_box = i.find_elements(By.XPATH, './/select')
                    child_calc_box = i.find_elements(By.XPATH, './/div[@class="help-text-trigger"]')
                    child_number_input = i.find_elements(By.XPATH, './/div[@class="number-wrapper"]')
                    child_phone_input = i.find_elements(By.XPATH, './/div[@class="phone-field-component__view-mode__cell"]')
                    key = key[0].text.replace("* ", "").replace(" ", "_")

                    if child_text_input:
                        dict_html[key] = " ".join(i.text for i in child_text_input)
                    elif child_email_input:
                        dict_html[key] = [i.text for i in child_email_input][0:5]
                    elif child_type_box:
                        dict_html[key] = [i.text for i in child_type_box if "selected" in i.get_attribute('class')]
                    elif child_select_box:
                        dict_html[key] = Select(child_select_box[0]).first_selected_option.text
                    elif child_calc_box:
                        dict_html[key] = child_calc_box[0].text
                    elif child_number_input:
                        dict_html[key] = child_number_input[0].text
                    elif child_phone_input:
                        index = int((len(child_phone_input) / 3))
                        dict_html[key] = child_phone_input[index].text

        # Add more information to dict
            dict_html['comment_period'] = comment_period
            partner_type = website.find_element(By.CLASS_NAME, 'app-name').text
            dict_html["partner_type"], dict_html["part_title"] = partner_type, part_title
            dict_html["Shop_Name"], dict_html['thread_num'] = shop_name, thread_num + 1
            dict_html["link_to_shop"], dict_html['text_of_task'] = link_to_shop, task_text

        # Test the data (that all elements in the dict are in the correct format)
            comment, new_id, error, dict_html = test_data(dict_html, task_dict)
            print(comment) if not comment else print("The data looks good!")

        # If there is a issue with formatting then send comment to Podio and go to next task
            if "wrong format" in error:
                if 'iban_details_response' in dict_html.keys() and \
                        "Can`t find country" in dict_html['iban_details_response']:
                    Admin_update.return_to_podio_with_updates(Admin_update(), comment, new_id,
                                                              error, dict_html, website)
                elif "There are no new shops to create." in comment:
                    Admin_update.return_to_podio_with_updates(Admin_update(), comment, new_id,
                                                              "", dict_html, website)
                    continue
                else:
                    Admin_update.return_to_podio_with_updates(Admin_update(), comment, new_id,
                                                              error, dict_html, website)
                    continue

            Admin_update.task_manager(Admin_update(), dict_html, task_text, website)

            print(f"{task_text} for {shop_name} was completed in "
                  f"{round((time.time() - start_time) / 60, 2)} min.".center(150), "thread_num",
                  dict_html['thread_num'])


class Admin_update():
    dict_location = {'DK': '045', 'SE': '046', 'NO': '047', 'NL': '031', 'BE': '032', 'PL': '048', 'CH': '041',
                     'ES': '034', 'IT': '039', 'FI': '358', 'FR': '033', 'DE': '049', 'UK': '044', 'CN': '086'}

    def open_admin(self, market, id, website):
        if market.lower() == 'pl':
            url = 'https://www.showroom.pl/'
        elif market.lower() == 'shwrm':
            url = 'https://www.showroom.pl/'
        elif market.lower() == 'uk':
            url = f'https://www.miinto.co.uk/'
        elif market.lower() == 'cn':
            url = f'https://china.miinto.net/'
        else:
            url = f'https://www.miinto.{market.lower()}/'

        # Go to edit tab
        sec_part_url = 'admin/shops-edit.php?action=edit&id=' + id
        website.get(url + sec_part_url)
        website.implicitly_wait(4)

        if website.find_elements(By.XPATH, '//*[@id="password"]'):
            username = website.find_element(By.XPATH, '//*[@id="username"]').send_keys("XXX")
            password = website.find_element(By.XPATH, '//*[@id="password"]').send_keys("XXX")
            website.find_element(By.XPATH, '/html/body/div[2]/div/div/form/fieldset/div[4]/div/input[2]').click()
            if market.lower() == 'cn':
                website.implicitly_wait(4)
                website.find_element(By.XPATH, '//button[@class="btn btn-mini login-user pull-right"]').click()
                time.sleep(2)

            website.get(url + sec_part_url)
            try:
                element = WebDriverWait(website, 10).until(EC.presence_of_element_located((By.NAME, "shopstreet")))
            except:
                time.sleep(2)

        return url, sec_part_url

    def open_pc(self, website):
        website.get('https://proxy-product.miinto.net/auth/login')
        website.implicitly_wait(4)
        time.sleep(1)

        if website.find_elements(By.XPATH, '//*[@id="username"]'):
            username = website.find_element(By.XPATH, '//*[@id="username"]').send_keys("XXX")
            password = website.find_element(By.XPATH, '//*[@id="password"]').send_keys("XXX")
            website.find_element(By.XPATH, '//*[@type="submit"]').click()
            website.implicitly_wait(4)

    def task_manager(self, dict_html, task, website):
        website.execute_script("window.open()")

    # First exclusion (Create new location in PC)
        if 'pc location' in task.lower():
            self.pc_location(dict_html, website)
            return

    # Second exclusion (update PC)
        elif 'add aliases' in task.lower():
            self.update_pc_loc_sales(dict_html, website, True)
            return

    # Check and exclude markets that need to be added
        elif "other markets" in task.lower():
            all_shop_ids = dict_html['All_Shop_IDs'].split(",")[0].replace("SHWRM", "PL")
            for i in dict_html['Markets_to_activate_for_the_partner']:
                if not i + "-" in dict_html['All_Shop_IDs']:
                    all_shop_ids += f',{i}-0'

            if all_shop_ids.count("-0") == 0:
                return
            all_shop_ids = all_shop_ids.split(",")

    # If this is other task then create list with markets and ids
        else:
            all_shop_ids = dict_html['All_Shop_IDs'].split(",")

    # Update information in all markets one by one
        new_ids = []
        for shop_id in all_shop_ids:
            website.switch_to.window(website.window_handles[3])

            market = shop_id.split("-")[0]
            id = shop_id.split("-")[1]

            try:
                url, sec_part_url = self.open_admin(market, id, website)
            except:
                print("There was an error when loading to the page. Trying again.", "thread_num",
                      dict_html['thread_num'])
                url, sec_part_url = self.open_admin(market, id, website)

            website.implicitly_wait(0)

        # Choosing task
            if "address/email" in task.lower() or "invoicing email" in task.lower():
                comment = self.update_adddress_email(dict_html, market, website)

            elif "order email" in task.lower():
                comment = self.update_order_email(dict_html, website)

            elif "Contact person" in task or "Shop phone number" in task:
                comment = self.update_contact_person(dict_html, website)

            elif "vat tax" in task.lower():
                comment = self.update_vat_tax(dict_html, website)

            elif "miinto shipping agreement" in task.lower():
                comment = self.update_miinto_agreement(dict_html, website)

            elif "commission" in task.lower().replace(" ", ""):
                if market == "CN":
                    continue
                comment = self.update_commission(dict_html, market, id, url, website)

                if "wasn`t changed due it`s the same as previous" in comment:
                    continue

            elif "name field change" in task:
                comment = self.update_shop_name(dict_html, website, market)

            elif "Price restriction" in task:
                if dict_html['partner_type'] == "Partners":
                    comment = self.update_price_restriction(dict_html, website)

                else:
                    comment = "Can`t add price restrictions to the Brand."
                    return self.return_to_podio_with_updates(comment, new_ids, task, dict_html, website)

            elif "other market" in task.lower() or "Create other admins" in task.lower():
            # Get data from the first market
                if market == dict_html["All_Shop_IDs"].split("-")[0]:
                    fields_to_fill, fields_to_select, input_dict, select_dict, all_checked_boxes,\
                    restr_value, order_dist = self.get_admin_setup(website)
                    continue

            # Create new markets with data from the first market
                else:
                    elements = [dict_html, market, fields_to_fill, fields_to_select, input_dict, select_dict,
                                all_checked_boxes, restr_value, order_dist, website]
                    comment = self.update_other_market(elements)

            elif "IBAN" in task:
                if "Multiple IBANs" in dict_html.keys():
                    try:
                        dict_html['Bank_Account_Number_-_IBAN_(format:_PL123456789)'] = dict_html[f"IBAN {market}"]
                        dict_html['Bank_Account_Number_-_SWIFT'] = dict_html[f"SWIFT {market}"]
                    except:
                        try:
                            dict_html['Bank_Account_Number_-_IBAN_(format:_PL123456789)'] = \
                                dict_html[f"Account {market}"]
                            dict_html['Bank_Account_Number_-_SWIFT'] = dict_html[f"CODE {market}"]
                        except:
                            comment = f"The wrong format, probably missing market in IBAN/SWIFT. \nCheck [{market}]"
                            return self.return_to_podio_with_updates(comment, "-", "wrong format", dict_html, website)

                comment = self.update_iban(dict_html, website, market)

                if "Bank transfer error" in comment:
                    comment = f"The account number was not updated on [{market}] market, due to the lack of " \
                              f"'account number' option in the admin. Please provide the IBAN & SWIFT number instead."
                    return self.return_to_podio_with_updates(comment, "-", "wrong format", dict_html, website)

            elif 'Status on Admin' in task:
                comment = self.status_on_admin(dict_html, website)
                if 'The status on admin is the same' in comment:
                    continue

            elif 'Additional shipping locations' in task:
                if market == "CN":
                    continue

            # Edit admins in other please then standard editing
                website.get(url + "admin/action/_login.php?login_as=" + id)
                website.implicitly_wait(4)

                comment = self.additional_shipping(dict_html, website, url)
                website.get(url + 'admin/action/_login.php?todo=admin_re_login')
                website.implicitly_wait(4)
                continue

        # Save changes
            save_button = website.find_element(By.XPATH, '//button[@class="btn btn-success"]')
            website.execute_script("arguments[0].click();", save_button)

        # Get save result
            time_start_while = time.time()
            success_fields = error_fields = False
            while not success_fields and not error_fields and 4 > (time.time() - time_start_while):
                success_fields = website.find_elements(By.XPATH, '//*[@class="alert alert-success alert--success"]')
                error_fields = website.find_elements(By.XPATH, '//*[@class="alert alert-error alert--error"]')

            if error_fields:
                error_message = "\n".join([i.text for i in error_fields])
                comment = f"\n\nSite Response: \nThere was error after trying to saved changes. \n" \
                          f"\n\n>{error_message} \n\n Task title: [{task}]"
                return self.return_to_podio_with_updates(comment, new_ids, task, dict_html, website)

            elif success_fields:
                success_message = "\n".join([i.text for i in success_fields])
                comment += f"\n\nSite Response: \n>{success_message}"

            else:
                comment = f"\n\nSite Response:\nThere was an connection error on the page."
                if "other market" in task.lower():
                    raise ConnectionError(comment)
                return self.task_manager(dict_html, task, website)

        # If new market was created then update Podio with new market
            if "other markets" in task.lower():
                new_shop_id = market + '-' + re.findall(r'\d{4}', website.current_url)[0]
                new_ids.append(new_shop_id)
                self.return_to_podio_with_updates(comment, [new_shop_id], "only update", dict_html, website)

        # If all is done then update Podio
        else:
            print(comment, "thread_num", dict_html['thread_num'])
            self.return_to_podio_with_updates(comment, new_ids, task, dict_html, website)

    def update_contact_person(self, dict_html, website):
        phone_number = website.find_element(By.XPATH, '//input[@name="shopphonenumber"]')

        contact_person = website.find_element(By.XPATH, '//input[@name="contactperson1"]')
        contact_person_email = website.find_element(By.XPATH, '//input[@name="contactemail1"]')
        position_1 = website.find_element(By.XPATH, '//input[@name="position1"]')

        contact_person_2 = website.find_element(By.XPATH, '//input[@name="contactperson2"]')
        contact_person_2_email = website.find_element(By.XPATH, '//input[@name="contactemail2"]')
        position_2 = website.find_element(By.XPATH, '//input[@name="position2"]')

        if not dict_html['Shop_phone_number_-_shipping_labels_and_customer_service'] == None:
            phone_number.clear()
            phone_number.send_keys(dict_html['Shop_phone_number_-_shipping_labels_and_customer_service'])

        contact_person.clear()
        contact_person.send_keys(dict_html['Contact_person_1_-_name_&_surname'])

        contact_person_email.clear()
        contact_person_email.send_keys(dict_html['Contact_person_-_emails'][0])

        position_1.clear()
        position_1.send_keys('-')

        try:
            if dict_html['Contact_person_-_emails'][1]:
                contact_person_2.clear()
                contact_person_2.send_keys(dict_html['Contact_person_2_-_name_&_surname'])

                contact_person_2_email.clear()
                contact_person_2_email.send_keys(dict_html['Contact_person_-_emails'][1])

                position_2.clear()
                position_2.send_keys('-')
        except:
            print('contact_person_2 is blank')

        return f"The task with change fields contact_person etc. was completed.\n" \
               f"\n > What was updated?\n" \
               f"\n > contact_person: \n[{contact_person.get_attribute('value')}]\n" \
               f"\n > contact_person_email: \n[{contact_person_email.get_attribute('value')}]\n" \
               f"\n > contact_person_2: \n[{contact_person_2.get_attribute('value')}]\n" \
               f"\n > contact_person_2_email: \n[{contact_person_2_email.get_attribute('value')}]\n" \
               f"\n > phone_number: \n[{phone_number.get_attribute('value')}]"

    def update_order_email(self, dict_html, website):
        order_email = website.find_element(By.XPATH, "/html/body/div[2]/div[2]/div[2]/form/div[2]/div[1]/input[1]")
        order_email.clear()
        order_email.send_keys(dict_html['Order_Email'])

        return f"The task with change field order_email was completed.\n" \
               f"What was updated?\n" \
               f"\n > order_email: \n[{order_email.get_attribute('value')}]"

    def update_adddress_email(self, dict_html, market, website):
        zip_code = website.find_element(By.XPATH, '//input[@id="shopzipcode"]')
        zip_code.clear()
        zip_code.send_keys(dict_html['Shipping_Address_-_Zip_code'])

        invoicing_zipcode = website.find_element(By.XPATH, '//input[@id="invoicingzipcode"]')
        invoicing_zipcode.clear()
        invoicing_zipcode.send_keys(dict_html['Invoicing_Address_-_Zipcode'])

        street_input = website.find_element(By.XPATH, '//input[@name="shopstreet"]')
        street_input.clear()
        street_input.send_keys(dict_html['Shipping_Address_-_Street street'])

        street2_input = website.find_element(By.XPATH, '//input[@name="shopstreet2"]')
        street2_input.clear()
        street2_input.send_keys(dict_html['Shipping_Address_-_Street street2'])

        invoicing_street = website.find_element(By.XPATH, '//input[@name="invoicingstreet"]')
        invoicing_street.clear()
        invoicing_street.send_keys(dict_html['Invoicing_Address_-_Street street'])

        invoicing_street2 = website.find_element(By.XPATH, '//input[@name="invoicingstreet2"]')
        invoicing_street2.clear()
        invoicing_street2.send_keys(dict_html['Invoicing_Address_-_Street street2'])

        invoicing_country = website.find_element(By.NAME, 'invoicingcontry')
        for country_shipping in Select(invoicing_country).options:
            if dict_html['Invoicing_Address_-_Country'].lower().replace(" ", "") == country_shipping.text.lower().replace(" ", ""):
                Select(invoicing_country).select_by_visible_text(country_shipping.text)
        if dict_html['Invoicing_Address_-_Country'] == "Nederland" and market in "DKSENO":
            Select(invoicing_country).select_by_value("Netherlands")

        invoicing_email = website.find_element(By.XPATH, '//input[@name="invoiceemails"]')
        invoicing_email.clear()
        invoicing_email.send_keys(";".join(dict_html['Invoicing_Emails']))

        select_country_shipping = website.find_element(By.NAME, 'shopcontry')
        for country_shipping in Select(select_country_shipping).options:
            if dict_html['Shipping_Address_-_Country'].lower().replace(" ", "") == country_shipping.text.lower().replace(" ", ""):
                Select(select_country_shipping).select_by_visible_text(country_shipping.text)
        if dict_html['Shipping_Address_-_Country'] == "Nederland" and market in "DKSENO":
            Select(select_country_shipping).select_by_value("Netherlands")

        shop_address_city = website.find_element(By.XPATH, '//input[@id="shopcity"]')
        shop_address_city.clear()
        shop_address_city.send_keys(dict_html['Shipping_Address_-_City'])

        invoicing_city = website.find_element(By.XPATH, '//input[@id="invoicingcity"]')
        invoicing_city.clear()
        invoicing_city.send_keys(dict_html['Invoicing_Address_-_City'])

        invoicing_zipcode = website.find_element(By.XPATH, '//input[@id="invoicingzipcode"]').get_attribute('value')
        zip_code = website.find_element(By.XPATH, '//input[@id="shopzipcode"]').get_attribute('value')
        return f"\nThe task with change fields address_email etc. was completed.\n" \
               f"\nWhat was updated?\n\n" \
               f"\nInvoicing address" \
               f"\n > invoicing_zipcode: \n[{invoicing_zipcode}]\n" \
               f"\n > invoicing_street: \n[{invoicing_street.get_attribute('value')}]\n" \
               f"\n > invoicing_country: \n[{Select(invoicing_country).first_selected_option.text}]\n" \
               f"\n > invoicing_city: \n[{invoicing_city.get_attribute('value')}]\n" \
               f"\n > invoicing_email: \n[{invoicing_email.get_attribute('value')}]\n" \
               f"\nShop address" \
               f"\n > zip_code: \n[{zip_code}]\n" \
               f"\n > country_shipping: \n[{Select(select_country_shipping).first_selected_option.text}]\n" \
               f"\n > shop_address_city: \n[{shop_address_city.get_attribute('value')}]\n" \
               f"\n > street_1: \n[{street_input.get_attribute('value')}]\n" \
               f"\n > street_2: \n[{street2_input.get_attribute('value')}]"

    def update_vat_tax(self, dict_html, website):
        cvr = '/html/body/div[2]/div[2]/div[2]/form/div[4]/div[1]/input[3]'
        website.find_element(By.XPATH, cvr).clear()
        website.find_element(By.XPATH, cvr).send_keys(dict_html['VAT_TAX_Number'])

        return f"The task with change field vat_tax_number was completed.\n" \
               f"What was updated?\n" \
               f"\n > cvr: \n[{website.find_element(By.XPATH, cvr).get_attribute('value')}]"

    def update_miinto_agreement(self, dict_html, website):
        shipping_service = website.find_element(By.XPATH, '//input[@class="feature-miinto-shipping-service"]')
        free_shipping_service = website.find_element(By.XPATH, '//input[@class="feature-free-miinto-shipping-service"]')

        uncheck_the_tickbox = [i.click() for i in [shipping_service, free_shipping_service] if i.is_selected()]

    # Select the tickbox
        if dict_html['Miinto_Shipping_Agreement'] == 'Yes - FREE shipping and returns':
            shipping_service.click()
            free_shipping_service.click()
        elif dict_html['Miinto_Shipping_Agreement'] == 'Yes':
            shipping_service.click()

        return f"The task with change field shipping_service was completed.\n" \
               f"What was updated?\n" \
               f"\n > shipping_service: \n[{dict_html['Miinto_Shipping_Agreement']}]"

    def update_shop_name(self, dict_html, website, market):
        shop_name = website.find_element(By.XPATH, '//input[@name="shopname"]')
        shop_name.clear()
        shop_name.send_keys(f"{dict_html['Shop_Name']} by Miinto" if market == "CN" else dict_html['Shop_Name'])

        legal_name = website.find_element(By.XPATH, '/html/body/div[2]/div[2]/div[2]/form/div[4]/div[1]/input[2]')
        legal_name.clear()
        legal_name.send_keys(dict_html['Shop_Name'] if dict_html['Legal_Name'] == "" else dict_html['Legal_Name'])

        return f"The task with change field shop_name was completed.\n" \
               f"What was updated?\n" \
               f"\n > shop_name: \n[{shop_name.get_attribute('value')}]\n" \
               f"\n > legal_name: \n[{legal_name.get_attribute('value')}]"

    def update_price_restriction(self, dict_html, website):
        price_res_box = website.find_element(By.XPATH, '//input[@class="feature-transfer-price-restriction"]')
        price_res_box.click() if not price_res_box.is_selected() else print("Box is selected.")

        price_res_input = website.find_element(By.XPATH, '//*[@class="feature-value-transfer-price-restriction"]')
        price_res_input.clear()
        price_res_input.send_keys(dict_html['Transfer_price_restriction_%'])

        return f"The task with change field price_restriction was completed.\n" \
               f"What was updated?\n" \
               f"\n > price_restriction: \n[{price_res_input.get_attribute('value')}]"

    def update_iban(self, dict_html, website, market):
        select_iban = Select(website.find_element(By.NAME, 'payment_method'))
        if f"Account {market}" in dict_html.keys():
            try:
                select_iban.select_by_visible_text("Bank transfer")
            except:
                return "Bank transfer error"
        else:
            select_iban.select_by_visible_text("IBAN/Swift")

        bic = website.find_elements(By.XPATH, '//input[@name="bank_reg"]')
        if bic and bic[0].is_displayed():
            bic[0].clear()
            bic[0].send_keys(dict_html['Bank_Account_Number_-_SWIFT'])

        iban = website.find_elements(By.XPATH, '//input[@name="bank_konto"]')
        if iban and iban[0].is_displayed():
            iban[0].clear()
            iban[0].send_keys(dict_html['Bank_Account_Number_-_IBAN_(format:_PL123456789)'])

        return f"\nThe task with change field iban was completed.\n" \
               f"What was updated?\n" \
               f"\n > iban/banknumber: \n[{iban[0].get_attribute('value')}]\n"

    def get_admin_setup(self, website):
        fields_to_fill = ['shopzipcode', 'invoicingzipcode', 'username', 'ordreemail', 'bank_reg',
                          'bank_konto', 'shopname', 'juridiskname', 'cvrnumber', 'shorttag', 'shopphonenumber',
                          'shopmobilnumber', 'shopfaxnumber', 'shopstreet', 'shopstreet2', 'website', 'contactperson1',
                          'position1', 'contactemail1', 'contactperson2', 'position2', 'contactemail2', 'shopcity',
                          'shopstate', 'invoicingcity', 'invoicingstate', 'invoiceemails', 'signupdate', 'startprice',
                          'shopsigupperson', 'invoicingstreet', 'invoicingstreet2', 'consultant', 'customercare']

        fields_to_select = ['activity', 'admin', 'payment_method', 'vat_zone',
                            'shopcontry', 'invoicingcontry', 'commission_reducer_type']

        input_dict = {}  # GET TEXT FIELDS
        for name in fields_to_fill:
            input_dict[name] = website.find_element(By.NAME, name).get_attribute("value")

        select_dict = {}  # GET SELECT FIELDS
        for name in fields_to_select:
            select_dict[name] = Select(
                website.find_element(By.XPATH, f'//*[@name="{name}"]')).first_selected_option.text

        all_checked_boxes = [i.get_attribute("class") for i in website.find_elements(By.TAG_NAME, "input") if i.is_selected()]

        restriction_xpath = '//input[@class="feature-value-transfer-price-restriction"]'
        restr_value = website.find_element(By.XPATH, restriction_xpath).get_attribute("value")

        dist_xpath = '//input[@class="feature-value-order-distribution-delay"]'
        order_dist = website.find_element(By.XPATH, dist_xpath).get_attribute("value")

        return fields_to_fill, fields_to_select, input_dict, select_dict, \
               all_checked_boxes, restr_value, order_dist

    def update_other_market(self, elements):
        dict_html, market, fields_to_fill, fields_to_select, input_dict, select_dict, all_checked_boxes, \
        restr_value, order_dist, website = elements

        vat_zones = pd.read_csv('vat_zones.csv', index_col=0)
        password = website.find_element(By.XPATH, '//input[@name="password"]')
        password.send_keys(dict_html['Password'])

        password2 = website.find_element(By.XPATH, '//input[@name="password2"]')
        password2.send_keys(dict_html['Password'])

    # Update in bulk Select fields
        for name in fields_to_select:
            element = Select(website.find_element(By.NAME, name))
            try:
                element.select_by_visible_text(select_dict[name])
            except:
                if 'country' in name:
                    element.select_by_value("Nederland")

    # Update in bulk Text fields
        for name in fields_to_fill:
            element = website.find_element(By.XPATH, f'//input[@name="{name}"]')
            if name == "signupdate":
                signup_date = [element.send_keys(i) for i in reversed(input_dict[name].split("-"))]
            else:
                element.clear()
                element.send_keys(input_dict[name])

    # Update in bulk Checkboxes
        for box_class in all_checked_boxes:
            element = website.find_element(By.CLASS_NAME, box_class)
            element.click()
            if box_class == "feature-transfer-price-restriction":
                price_restriction_input = website.find_element(By.XPATH, '//input[@class="feature-value-transfer-price-restriction"]')
                price_restriction_input.send_keys(restr_value)
            elif box_class == "feature-order-distribution-delay":
                order_dist_delay = website.find_element(By.XPATH, '//input[@class="feature-value-order-distribution-delay"]')
                order_dist_delay.send_keys(order_dist)

    # Update in bulk other fields
        vat_zone = Select(website.find_element(By.XPATH, '//select[@name="vat_zone"]'))
        if dict_html['Home_Market'] == 'UK':
            vat_zone.select_by_visible_text('foreign')
        else:
            try:
                vat_zone.select_by_visible_text(vat_zones[dict_html['Home_Market']][market])
            except:
                vat_zone.select_by_visible_text('eu')

        if market == "CN":
            shop_name = website.find_element(By.XPATH, "/html/body/div[2]/div[2]/div[2]/form/div[4]/div[1]/input[1]")
            shop_name.clear()
            shop_name.send_keys(f"{dict_html['Shop_Name']} by Miinto")

        return f"The task other markets field change was completed.\n" \
               f"What was updated?\n" \
               f"\n > All new markets were added to admins."

    def update_commission(self, dict_html, market, id, url, website):
        partner_type_box = {"Partners": ["Name: Shop", "Store-"], "Brands": ["Name: Brand", "Brand-"]}
        vat_rate = {'SE': 25, 'DE': 19, 'DK': 25, 'BE': 21, 'PL': 23, "SHWRM": 23, 'NL': 21, 'IT': 22,
                    'ES': 21, 'FR': 20, 'FI': 24, 'NO': 25, 'UK': 20, 'CH': 7.7}
        
        pure_comm = dict_html['Pure_commission_to_be_charged_on_balanced_orders']
        new_comm = round(float(pure_comm) * ((vat_rate[market] / 100) + 1), 2)

        reducer_type_field = Select(website.find_element(By.XPATH, '//select[@name="commission_reducer_type"]'))
        shop_name = website.find_element(By.XPATH, '//input[@name="shopname"]').get_attribute("value")
        partner_type = Select(website.find_element(By.XPATH, '//select[@name="admin"]')).first_selected_option.text.lower()
        full_name = f'{shop_name} ({partner_type}) ({reducer_type_field.first_selected_option.get_attribute("value")})'

    # Go to commission tool
        website.execute_script("window.open()")
        website.switch_to.window(website.window_handles[4])
        website.get(url + 'admin/tools/commission')
        website.implicitly_wait(4)

    # Find the correct column and box to drag it
        drag = [i for i in website.find_elements(By.XPATH, f"//li[contains(@data-default-block-type, '"
                                                           f"{partner_type_box['Partners'][1]}')]")][0]
        try:
            drop = [i for i in website.find_elements(By.XPATH, '//div[@class="commission-tools__block js-rules-list"]')
                    if partner_type_box[dict_html['partner_type']][0].lower().replace(" ", "") in
                    i.text.lower().replace(" ", "")][0]
            
        except:
            drop = [i for i in website.find_elements(By.XPATH, '//div[@class="commission-tools__block js-rules-list"]')
                    if partner_type_box["Partners"][0].lower().replace(" ", "") in i.text.lower().replace(" ", "")][0]

        drop_offset = {"x": drop.location['x'] - drag.location['x'], "y": drop.location['y'] - drag.location['y'] + 115}
        column_width = {"left": drop.location["x"] - 14, "right": drop.location["x"] + drop.size["width"] + 52}
        default_commission = drop.find_elements(By.XPATH, './/span[@class="commission-tools__block-title"]')[1].text

        try:  # Searching existing box
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

                    if shop.get_attribute('id').split("-")[-1] == id:
                        break
                        
                close_edit = website.find_element(By.XPATH, '//*[@id="ruleForm"]/div/input[2]').click()
                
            else:
                if not all_shops or shop.get_attribute('id').split("-")[-1] != id:
                    raise ValueError(f"Can`t find shop id in commission tool - market [{market}]")
    
        except:
            print("create new commission box for the new shop.", "thread_num", dict_html['thread_num'])
            ActionChains(website).drag_and_drop_by_offset(drag, drop_offset["x"], drop_offset["y"]).perform()
            try:
                WebDriverWait(website, 10).until(EC.presence_of_element_located((By.XPATH, '//*[@id="ruleForm"]')))
            except:
                time.sleep(2)

            dropdown = website.find_element(By.XPATH, '//*[@id="ruleForm"]/span/span[1]/span/span[2]')
            dropdown.click()

            all_shops = website.find_elements(By.XPATH, f'//li[text()="{full_name}"]')
            shop = [i for i in all_shops if i.get_attribute('id').split("-")[-1] == id][0]
            shop.click()

        time.sleep(3)
        name = website.find_element(By.XPATH, '//*[@id="ruleForm"]/input[1]')
        name.clear()
        name.send_keys(dict_html['Shop_Name'])

        commission_value = website.find_element(By.XPATH, '//*[@id="ruleForm"]/input[2]')
        commission_value.clear()
        commission_value.send_keys(f'{new_comm}')

        accept_changes = website.find_element(By.XPATH, '//*[@id="ruleForm"]/div/input[1]')
        try:
            website.execute_script("arguments[0].click();", accept_changes)
            while website.find_elements(By.XPATH, '//*[@id="ruleForm"]'):  # Wait until the window disappear
                time.sleep(1)
        except:
            time.sleep(2)
            accept_changes = website.find_element(By.XPATH, '//*[@id="ruleForm"]/div/input[1]')
            if accept_changes.is_displayed():
                website.execute_script("arguments[0].click();", accept_changes)

        while website.find_elements(By.XPATH, '//*[@id="ruleForm"]'):  # Wait until the window disappear
            time.sleep(1)

        save_changes = website.find_element(By.XPATH, '//*[@id="main-form"]/button')
        website.execute_script("arguments[0].click();", save_changes)
        website.implicitly_wait(4)
        time.sleep(1)

        while website.find_element(By.XPATH, '/html/body/div[2]/div[2]/div[2]/div[3]/div[3]/span').is_displayed():
            website.implicitly_wait(6)
            time.sleep(1)
            website.execute_script("arguments[0].click();", save_changes)

        all_default_comm = set([float(i.text.split(" ")[0]) for i in website.find_elements(By.XPATH,
                                                                                           '//span[@class="commission-tools__block-title"]')
                                if "%" in i.text])
        if max(all_default_comm) >= float(new_comm) >= min(all_default_comm):
            if max(all_default_comm) > float(default_commission.split(" ")[0]):
                reducer_type = "min"
            elif max(all_default_comm) == float(default_commission.split(" ")[0]):
                reducer_type = "max"
        else:
            if float(new_comm) < float(default_commission.replace(' %', '')):
                reducer_type = "min"
            elif float(new_comm) > float(default_commission.replace(' %', '')):
                reducer_type = "max"

        website.switch_to.window(website.window_handles[3])
        
        reducer_field = Select(website.find_element(By.XPATH, '//select[@name="commission_reducer_type"]'))
        if reducer_field.first_selected_option.get_attribute("value") != reducer_type:
            reducer_field.select_by_value(reducer_type)
            reducer_type = f"was changed to [{reducer_type}]"
            
        else:
            reducer_type = f"wasn`t changed due it`s the same as previous [{reducer_type}]"

        return "The task with change commission was completed.\n" \
               "What was updated? \n" \
               f"\n > Commission was changed to \n[{dict_html['Pure_commission_to_be_charged_on_balanced_orders']}]\n" \
               f"\n > Commission after conversion in {market} \n[{new_comm}]\n" \
               f"\n > reducer type  \n[{reducer_type}]"

    def status_on_admin(self, dict_html, website):
        website.refresh()
        website.implicitly_wait(4)
        status_on_admin = Select(website.find_element(By.XPATH, '//select[@name="activity"]'))

        status_before = status_on_admin.first_selected_option.text

        if "Churn Negotiation" in dict_html['Status_on_Admin'] or \
                "Churn Requested" in dict_html['Status_on_Admin'] or \
                "Temp Closed - Rejection Rate" in dict_html['Status_on_Admin'] or \
                "Temp Closed - Holidays" in dict_html['Status_on_Admin']:
            status_on_admin.select_by_visible_text("Temp. closed")

        elif "Churn Closed" in dict_html['Status_on_Admin']:
            status_on_admin.select_by_visible_text("Closed")

        elif "Active" in dict_html['Status_on_Admin']:
            status_on_admin.select_by_visible_text("Miinto Full")

        if status_before == status_on_admin.first_selected_option.text:
            return "The status on admin is the same as in Podio the changes is not necessary." \
                   f"\n > Status on Admin: \n[{status_on_admin.first_selected_option.text}]\n"

        return "The task with change Status on Admin was completed.\n" \
               "What was updated? \n" \
               f"\n > Status on Admin was changed to \n[{status_on_admin.first_selected_option.text}]\n"

    def pc_location(self, dict_html, website):
        website.switch_to.window(website.window_handles[2])

        if "PC_location_name" in dict_html.keys():
            return self.return_to_podio_with_updates("The location is created already", "-", "-", dict_html, website)

        primary_id = dict_html["All_Shop_IDs"].split(",")[0].split("-")[1]
        primary_market = dict_html["All_Shop_IDs"].split(",")[0].split("-")[0]
        
        prefix = "S" if dict_html["partner_type"] == "Partners" else "B"
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
        website.implicitly_wait(4)

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
        except:
            select_language = website.find_element(By.XPATH, f"//li[text()='English']").click()

        active = website.find_element(By.XPATH, '//*[@id="locationIsActive"]')
        website.execute_script("arguments[0].setAttribute('checked',arguments[1])", active, "checked")

        submit = website.find_element(By.XPATH, '/html/body/div[1]/div/main/form/div[6]/button').click()
        
        self.update_pc_loc_sales(dict_html, website, False)

    def update_pc_loc_sales(self, dict_html, website, login):
        if login:
            website.switch_to.window(website.window_handles[3])
            self.open_pc(website)

        if "PC_location_name" not in dict_html.keys():
            return self.return_to_podio_with_updates("Can`t find PC_location_name", "", "", dict_html, website)

        website.get('https://proxy-product.miinto.net/locations')
        website.implicitly_wait(4)

        try:
            while dict_html["PC_location_name"] not in website.find_element(By.XPATH, '//tbody').get_attribute("textContent"):
                next_page = website.find_element(By.XPATH, '//*[@class="feather feather-chevron-right"]').click()
                website.implicitly_wait(4)
        except:
            comment = "error: Can`t find Pc location name in PC."
            return self.return_to_podio_with_updates(comment, "", "", dict_html, website)

        cells = website.find_elements(By.XPATH, '//tr')
        edit_link = [i.find_element(By.XPATH, './/a[@class="btn btn-outline-primary"]').get_attribute("href")
                     for i in cells if dict_html["PC_location_name"] in i.get_attribute("textContent")][0]

        website.get(edit_link)
        website.implicitly_wait(4)
        location_url = website.current_url

    # delete existing locations
        website.find_element(By.XPATH, '//button[@id="nav-alias-tab"]').click()
        time.sleep(1)
        del_links = [i.get_attribute("href") for i in website.find_elements(By.XPATH, '//a')
                     if "alias" in i.get_attribute("href")]
        for link in del_links:
            website.get(link)
            website.implicitly_wait(4)

            website.find_element(By.XPATH, '/html/body/div[1]/div/main/form/div[2]/button').click()  # Submit
            website.implicitly_wait(4)

        while True:
            try:
                website.get(edit_link)
                website.implicitly_wait(4)

            # Collect existing locations
                website.find_element(By.XPATH, '//button[@id="nav-alias-tab"]').click()
                time.sleep(1)
                existing_loc = [i.get_attribute("textContent").split("-")[-1] for i in
                                website.find_elements(By.XPATH, '//td') if "1-m!i!s" in i.get_attribute("textContent")]

                for i, shop_id in enumerate(dict_html["All_Shop_IDs"].split(",")):
                    market, market_id = shop_id.split("-")[0], shop_id.split("-")[1]
                    unifed_loc = f"1-m!i!s-{self.dict_location[market]}-{market_id}"

                # Aliass
                    website.get(f"{location_url}/alias")
                    website.implicitly_wait(4)

                    if i > 0 and market_id not in existing_loc:
                        unified_id = website.find_element(By.XPATH, '//*[@id="locationAliasUnifiedId"]')
                        unified_id.send_keys(unifed_loc)

                        website.find_element(By.XPATH,
                                             '/html/body/div[1]/div/main/form/div[2]/button').click()  # Submit
                        website.implicitly_wait(4)

                else:
                    break
            except:
                continue

    # Response
        website.get(edit_link)
        website.implicitly_wait(4)

        website.find_element(By.XPATH, '//button[@id="nav-alias-tab"]').click()
        time.sleep(0.5)
        existing_loc = [i.get_attribute("textContent").split("-")[-1] for i in
                        website.find_elements(By.XPATH, '//td') if "1-m!i!s" in i.get_attribute("textContent")]

        comment = "The task with pc locations was completed.\n" \
                  "What was updated? \n" \
                  f"\n > Active Locations: \n{dict_html['All_Shop_IDs'].split(',')[0].split('-')[1]},{existing_loc}\n"

        self.return_to_podio_with_updates(comment, "", "", dict_html, website)

    def additional_shipping(self, dict_html, website, url):
        esentail_keys = ['zipcode', 'name', 'street', 'street2', 'city']

        website.get(url + 'admin/shop-addresses.php')
        website.implicitly_wait(4)
        time.sleep(1)

        links = [i.find_element(By.XPATH, '../.').get_attribute("href") for i in
                 website.find_elements(By.XPATH, '//button[@class="btn btn-mini"]')
                 if i.find_element(By.XPATH, '../.').get_attribute("href")]

        for link in links:
            website.get(link)
            website.implicitly_wait(4)

            website.find_element(By.XPATH, '//button[@class="btn btn-danger address-delete"]').click()
            time.sleep(1)
            website.find_element(By.XPATH, '//button[@class="confirm"]').click()

            accept = website.find_elements(By.XPATH, '//div[contains(@class, "alert alert")]')
            while not accept:
                time.sleep(0.2)

        for address_num in dict_html["shipping_locations"]:
            address_dict = dict_html["shipping_locations"][address_num]

            website.get(url + 'admin/shop-addresses.php?method=getAddressCreateForm')
            website.implicitly_wait(4)

            address_type = Select(website.find_element(By.XPATH, f'//select[@name="address_type_id"]'))
            address_type.select_by_value("1") if "sender" in address_num.lower() else address_type.select_by_value("2")

            for input_name in esentail_keys:
                field = website.find_element(By.XPATH, f'//input[@name="{input_name}"]')
                field.clear()
                field.send_keys(address_dict[input_name])

            country = Select(website.find_element(By.XPATH, f'//select[@name="country_code"]'))
            country.select_by_value(address_dict['countrycode'])
            time.sleep(2)

            website.find_element(By.XPATH, '//button[@type="submit"]').click()
            accept = website.find_elements(By.XPATH, '//div[contains(@class, "alert alert")]')
            while not accept:
                time.sleep(0.2)
            time.sleep(1)

        return "Additional shipping addresses were updated in Admins."

    def return_to_podio_with_updates(self, comment, new_id, task, dict_html, website):
        website.switch_to.window(website.window_handles[2])
        check = re.sub('[^a-zA-Z0-9]', '', " ".join(comment.split("\n"))).lower()

        # add a comment
        if task == "only update":
            all_ids_field = website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[2]/div')
            text = all_ids_field.text
            all_ids_field.click()

            all_id_input = website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[2]/div/input')
            all_id_input.clear()
            all_id_input.send_keys(f"{text},{','.join(new_id)}")

            website.find_element(By.XPATH, '//*[@id="all-shop-ids"]/div[1]/div[1]/div/div[2]').click()
            time.sleep(1)
            return

        while True:
            try:
                dupl_com = True
                website.find_element(By.XPATH, '//li[@data-type="comment"]').click()
                while len(website.find_elements(By.XPATH, '//time')) + \
                        len(website.find_elements(By.XPATH, '//div[@class="author"]')) < 5:
                    time.sleep(1)
                time.sleep(1)

                msgs = website.find_elements(By.XPATH, '//div[@class="activity-group"]')
                for msg in msgs:
                    comm_date = msg.find_element(By.XPATH, './/time')
                    comm_date = datetime.strptime(comm_date.get_attribute('datetime').split(" ")[0], "%Y-%m-%d").date()

                    author = msg.find_element(By.XPATH, './/div[@class="author"]').text

                    text = " ".join(i.text.replace(" ", "") for i in msg.find_elements(By.XPATH, './/p'))
                    text = re.sub('[^a-zA-Z0-9]', '', text.lower())

                    if "Update Admins" in author and (datetime.today().date() - comm_date).days < \
                            dict_html['comment_period'] and text != "" and check in text:
                        dupl_com = 'Comment not added. (Duplicate).'
                        print(dupl_com)
                        break
            except:
                continue
            break

        if dupl_com != "Comment not added. (Duplicate).":
            table = pd.DataFrame([[dict_html["Shop_Name"], dict_html['text_of_task'], comment,
                                   dict_html["link_to_shop"], datetime.now()]])
            g_sheets(col=1, sheet_name="Bot msgs", data=table)

            website.refresh()
            while not website.find_elements(By.XPATH, '//textarea[@placeholder="Add a comment"]'):
                time.sleep(1)
            time.sleep(1)

            text_box = website.find_element(By.XPATH, '//textarea[@placeholder="Add a comment"]')
            text_box.click()
            try:
                text_box.send_keys("@")
                text_box.send_keys(dict_html['task_requester'][0:3])
                text_box.send_keys(dict_html['task_requester'][3:7])

                time.sleep(1)
                text_box.send_keys(dict_html['task_requester'][7:20])

                time.sleep(1)
                website.implicitly_wait(4)

                user = [s.get_attribute("data-id") for i in website.find_elements(By.XPATH, '//span[@class="value"]')
                        if i.text == dict_html['task_requester'] for s in i.find_element(By.XPATH, '../../../..//../.').
                        find_elements(By.XPATH, './/li[@data-group-id="profiles"]') if s.get_attribute("data-id")]

                text_box.clear()
                text_box.send_keys(f"@[{dict_html['task_requester']}](user:{user[0]}) \n\n")
                text_box.send_keys(comment.replace("_", " "))
            except:
                text_box.clear()
                text_box.send_keys(comment.replace("_", " "))

            website.implicitly_wait(4)
            website.find_element(By.XPATH, '//button[@label="Add"]').click()
            time.sleep(1)

    # click on the tasks tick box
        if "error" not in comment and "wrong format" not in task:
            website.switch_to.window(website.window_handles[1])
            website.refresh()
            website.implicitly_wait(5)

            box = website.find_element(By.XPATH, '//*[@id="task-permalink"]/div/div[1]/div[1]/div[1]/span/span/img')
            website.execute_script("arguments[0].click();", box)


class GUI(Podio_data, Admin_update):
    tasks = {"Add commission": ['All_Shop_IDs', 'Pure_commission_to_be_charged_on_balanced_orders', 'Shop_Name',
                                'Full_Commission_From_Contract'],
             "commission": ['All_Shop_IDs', 'Pure_commission_to_be_charged_on_balanced_orders', 'Shop_Name',
                            'Full_Commission_From_Contract'],
             "Order email": ['All_Shop_IDs', 'Order_Email'],
             "VAT TAX": ['All_Shop_IDs', 'VAT_TAX_Number'],
             "Miinto shipping agreement": ['All_Shop_IDs', 'Miinto_Shipping_Agreement'],
             "IBAN": ['All_Shop_IDs', 'Bank_Account_Number_-_IBAN_(format:_PL123456789)',
                      'Bank_Account_Number_-_SWIFT'],
             "Address/email": ['All_Shop_IDs', 'Shipping_Address_-_Street',
                               'Shipping_Address_-_Zip_code', 'Shipping_Address_-_City',
                               'Shipping_Address_-_Country', 'Invoicing_Address_-_Street',
                               'Invoicing_Address_-_Zipcode', 'Invoicing_Address_-_City',
                               'Invoicing_Address_-_Country', 'Invoicing_Emails'],
             "Invoicing Email": ['All_Shop_IDs', 'Shipping_Address_-_Street',
                                 'Shipping_Address_-_Zip_code', 'Shipping_Address_-_City',
                                 'Shipping_Address_-_Country', 'Invoicing_Address_-_Street',
                                 'Invoicing_Address_-_Zipcode', 'Invoicing_Address_-_City',
                                 'Invoicing_Address_-_Country', 'Invoicing_Emails'],
             "Contact person": ['All_Shop_IDs', 'Contact_person_1_-_name_&_surname',
                                'Contact_person_2_-_name_&_surname', 'Home_Market',
                                'Shop_phone_number_-_shipping_labels_and_customer_service', 'Contact_person_-_emails'],
             "name field change": ['All_Shop_IDs', 'Shop_Name', 'Legal_Name'],
             "other markets": ['All_Shop_IDs', 'Markets_to_activate_for_the_partner', 'Password', 'Home_Market'],
             "Create other admins": ['All_Shop_IDs', 'Markets_to_activate_for_the_partner', 'Password', 'Home_Market'],
             "Price restriction": ['All_Shop_IDs', 'Transfer_price_restriction_%'],
             "Shop phone number": ['All_Shop_IDs', 'Contact_person_1_-_name_&_surname', 'Home_Market',
                                   'Shop_phone_number_-_shipping_labels_and_customer_service',
                                   'Contact_person_2_-_name_&_surname', 'Contact_person_-_emails'],
             "Status on Admin": ['All_Shop_IDs', 'Status_on_Admin'],
             "PC Location": ['All_Shop_IDs', 'Home_Market', 'Shop_Name', 'PC_location_name'],
             'Add aliases': ['All_Shop_IDs', 'Home_Market', 'Shop_Name', 'PC_location_name'],
             'Additional shipping locations': ['All_Shop_IDs', 'Additional_shipping_locations_-_Sender',
                                               'Return_address']
             }
    chromedriver_options = None

    @Gooey(
        program_name="Agi Bot - Update",
        program_description="Update Admins with Agi Bot!",
        terminal_font_color='black',
        terminal_panel_color='white',
        progress_regex=r"^progress: (\d+)/(\d+)$",
        progress_expr="x[0] / x[1] * 100",
        disable_progress_bar_animation=False,
        default_size=(810, 630),
        timing_options={'show_time_remaining': True, 'hide_time_remaining_on_complete': True}
    )
    def handle(self):
        parser = GooeyParser()

        parser.add_argument("--threads_num", metavar="How many processes do you need at once?", widget="Slider",
                            default=6, gooey_options={'min': 1, 'max': 6}, type=int)
        parser.add_argument("--comment_period", metavar="After [X] days I should add the same comment?",
                            widget="Slider", default=3, gooey_options={'min': 1, 'max': 10}, type=int)

        checkboxes = parser.add_argument_group('Main checkboxes', gooey_options={'columns': 1 - 2})
        checkboxes.add_argument("--headless_website", metavar=" ", widget="BlockCheckbox",
                                default=True, action='store_false',
                                gooey_options={'checkbox_label': "headless website", 'show_label': True})
        checkboxes.add_argument("--All_tasks", metavar=" ", widget="BlockCheckbox",
                                default=True, action='store_false',
                                gooey_options={'checkbox_label': "All tasks except 'Add commission'", 'show_label': True})

    # Dynamic tick boxes to choose tasks that need to be done
        for index, task_key in enumerate(self.tasks.keys()):
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
                                        gooey_options={'checkbox_label': task_key.replace(' ', '_'), 'show_label': True})

        user_inputs = vars(parser.parse_args())

    # Get only tasks that were checked
        if user_inputs['All_tasks']:  # if All tasks option was blank
            tasks_dict = {}
            for task_key in user_inputs:
                if task_key.replace("_", " ") in self.tasks and user_inputs[task_key]:
                    tasks_dict[task_key.replace("_", " ")] = self.tasks[task_key.replace("_", " ")]

        else:  # If All tasks option was clicked
            tasks_dict = self.tasks
            tasks_dict.pop("Add commission", None)  # This task can't be run with headless option

        self.setup_chromedriver_options(user_inputs)
        self.threads(user_inputs['threads_num'], tasks_dict, user_inputs['comment_period'])

    def setup_chromedriver_options(self, user_inputs):
        self.chromedriver_options = webdriver.ChromeOptions()

        self.chromedriver_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        self.chromedriver_options.add_argument("--disable-extensions")
        self.chromedriver_options.add_argument("--window-size=1920,1080")
        self.chromedriver_options.add_argument("--disable-gpu")

        prefs = {"profile.default_content_settings.popups": 2, "download.default_directory": os.getcwd()}
        self.chromedriver_options.add_experimental_option("prefs", prefs)

        if not user_inputs["headless_website"] and not user_inputs["Add_commission"]:
            self.chromedriver_options.add_argument("--headless")

    def threads(self, threads_num, tasks_dict, comment_period):
        os.environ["WDM_LOG_LEVEL"] = "0"
        website = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()),
                                   options=self.chromedriver_options)

    # Collect tasks before update
        tasks_list = self.get_tasks(website, tasks_dict)
        np.random.shuffle(tasks_list)
        website.close()

    # Give different tasks between all threads
        threads = list()
        l = 0
        for index in range(threads_num):
            start_index = l
            l += int(len(tasks_list) / threads_num)

            if index == threads_num - 1:
                print(index)
                end_index = len(tasks_list)

            else:
                end_index = l

            if end_index > len(tasks_list):
                end_index = len(tasks_list)

            print(start_index, end_index, "thread_num", index)

            chrome_service1 = ChromeService(ChromeDriverManager().install())
            # chrome_service1.creationflags = CREATE_NO_WINDOW
            website1 = webdriver.Chrome(options=self.chromedriver_options, service=chrome_service1)
            x = threading.Thread(target=self.get_podio_data, args=(tasks_list[start_index:end_index], website1,
                                                                   start_index, end_index, index, comment_period))
            threads.append(x)
            x.start()

        for index, thread in enumerate(threads):
            thread.join()


if __name__ == "__main__":
    gui = GUI()
    gui.handle()
