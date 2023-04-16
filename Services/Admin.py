import time

from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from datetime import datetime

from Services.PaMS import PaMS


class Admin:
    def __init__(self, credentials: dict):
        self.credentials = credentials
        self.addi_shipping_fields = ['zipcode', 'name', 'street', 'street2', 'city']
        self.vat_rate = {'SE': 25, 'DE': 19, 'DK': 25, 'BE': 21, 'PL': 23, "SHWRM": 23, 'NL': 21, 'IT': 22,
                         'ES': 21, 'FR': 20, 'FI': 24, 'NO': 25, 'UK': 20, 'CH': 7.7}

    def login(self, website, market: str, url: str, sec_part_url: str):
        website.find_element(By.XPATH, '//*[@id="username"]').send_keys(self.credentials['username_admin'])
        website.find_element(By.XPATH, '//*[@id="password"]').send_keys(self.credentials['password_admin'])
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
        action, comment = PaMS().update_edit_view(website, data)
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
