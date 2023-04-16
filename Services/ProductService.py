import time
import pycountry

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class ProductService:
    def __init__(self, credentials: dict):
        self.credentials = credentials
        self.dict_location = {'DK': '045', 'SE': '046', 'NO': '047', 'NL': '031', 'BE': '032',
                              'PL': '048', 'CH': '041', 'ES': '034', 'IT': '039', 'FI': '358',
                              'FR': '033', 'DE': '049', 'UK': '044', 'CN': '086'}

    def open_pc(self, website) -> None:
        website.get('https://proxy-product.miinto.net/auth/login')
        while not website.find_elements(By.XPATH, '//*[@id="username"]') \
                and not website.find_elements(By.XPATH, "//h1[contains(text(), 'Products')]"):
            time.sleep(0.5)

        if website.find_elements(By.XPATH, '//*[@id="username"]'):
            website.find_element(By.XPATH, '//*[@id="username"]').send_keys(self.credentials['username_pc'])
            website.find_element(By.XPATH, '//*[@id="password"]').send_keys(self.credentials['password_pc'])
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
