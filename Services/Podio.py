import pandas as pd
import pycountry
import warnings
import requests
import re

from bs4 import MarkupResemblesLocatorWarning
from schwifty import IBAN, bic
from phonenumbers import format_number, parse, PhoneNumberFormat

from bs4 import BeautifulSoup as bs
from multiprocessing import Pool
from datetime import datetime

from Services.GoogleSheet import GoogleSheet


class Podio:
    def __init__(self, data: dict, access_tokens: list, credentials: dict):
        self.access_tokens = access_tokens
        self.credentials = credentials
        self.data = data

    def __get_access_token__(self, client_id: str, client_secret: str) -> str:
        # Set the client ID, client secret, username, and password
        data = {
            'grant_type': 'password',
            'client_id': client_id,
            'client_secret': client_secret,
            'username': self.credentials['username_podio'],
            'password': self.credentials['password_podio']
        }

        # Make the HTTP request to obtain the access token
        response = requests.post('https://podio.com/oauth/token', data=data)

        # Parse the response from the Podio API
        data = response.json()

        if response.status_code != 200:
            raise ConnectionRefusedError(data["error_description"])

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
        comment, new_id, error = TestData().test_data(podio_data, task_dict, self.data)
        print("There is an issue") if comment else print("The data looks good!")

        # If there is an issue with formatting then send comment to Podio and go to next task
        if "wrong format" in error:
            if "There are no new shops to create." in comment:
                self.complete_task(self.data['task_id'])
            return comment, self.data | podio_data
        return comment, self.data | podio_data

    def add_username_password(self) -> (str, str):
        fields_ids = ['222617769', '193610265'] \
            if self.data['partner_type'] == "brands" \
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


class TestData:
    def test_data(self, podio_data, task_dict, data):
        podio_data["shipping_locations"] = {}
        for field in task_dict:
            comment = False

            try:
                if field.lower() in ['full_commission_from_contract', 'pc_location_name', "display_miinto_address",
                                     "Date_of_signing"]:
                    continue

                elif field in ["Shop_Name", "Brand_Name"]:
                    podio_data[field] = data["Partner_Name"]

                elif "partner_type" in field:
                    data["shop_type"] = "Brand" if "brand" in data[field] else "Shop"

                elif "shippingAddresses.0.name" in field:
                    podio_data[field] = data["Partner_Name"]

                elif "Username" in field and "Username" not in podio_data:
                    podio_data['Username'] = podio_data['Order_Email']

                elif "Password" in field and "Password" not in podio_data:
                    d = podio_data['Date_of_signing'][0]
                    v = podio_data['VAT_TAX_Number']
                    podio_data['Password'] = str(d.day).zfill(2) + str(d.month).zfill(2) + 'Success.' + v[-2:]

                elif 'consultant' in field or 'customercare' in field or 'Signed_by' in field:
                    podio_data[field] = "Update Admins"

                elif "subscriptionType" in field:
                    podio_data[field] = "Standard"

                elif 'Transfer_price_restriction' in field:
                    if field not in podio_data.keys():
                        podio_data[field] = 50

                elif 'Order_distribution_delay' in field:
                    if field not in podio_data.keys() or podio_data[field] == "":
                        podio_data[field] = False

                elif "Miinto_Shipping_Agreement" in field:
                    if "FREE" in podio_data[field]:
                        podio_data['miinto_shipping_service'] = True
                        podio_data['free_miinto_shipping_service'] = True

                    elif podio_data[field] == "Yes":
                        podio_data['miinto_shipping_service'] = True
                        podio_data['free_miinto_shipping_service'] = False

                    else:
                        podio_data['miinto_shipping_service'] = False
                        podio_data['free_miinto_shipping_service'] = False

                elif "country" in field.lower():
                    if podio_data[field] == "No value":
                        raise ValueError("Country cant be empty.")

                elif "Status_on_Admin" in field:
                    if podio_data[field] in ["Churn Requested", "Temp Closed - Rejection Rate",
                                             "Temp Closed - Holidays", "Churn Negotiation"]:
                        podio_data[field] = "Temp. Closed"

                    elif "Churn Closed" in podio_data[field]:
                        podio_data[field] = "Closed"

                    elif "Active" in podio_data[field]:
                        podio_data[field] = "Miinto Full"

                elif "street" in field.lower():
                    podio_data[f'{field} street'] = podio_data[f'{field} street2'] = ""
                    for word in podio_data[field].replace("\n", " ").split(" "):
                        if len(podio_data[f'{field} street'] + " " + word) <= 30:
                            podio_data[f'{field} street'] = podio_data[f'{field} street'] + " " + word
                        elif len(podio_data[f'{field} street2'] + " " + word) <= 30:
                            podio_data[f'{field} street2'] = podio_data[f'{field} street2'] + " " + word

                elif 'IBAN' in field:
                    try:
                        if IBAN(podio_data[field]).bic is not None:
                            swift = IBAN(podio_data[field]).bic.compact
                        podio_data[field] = IBAN(podio_data[field]).compact
                    except Exception as e:
                        if podio_data[field].count(";") <= 0:
                            raise ValueError(f'Incorrect {field}') from e
                        podio_data["Multiple IBANs"] = True

                        for i in podio_data[field].replace(" ", "").replace("\n", "").split(";"):
                            if i != "":
                                if "IBAN" in i:
                                    i = i.replace(i.split("IBAN:")[1], IBAN(i.split("IBAN:")[1]).compact)

                                    for market in i.split("IBAN:")[0].split(","):
                                        podio_data[f"IBAN {market}"] = i.split("IBAN:")[1]

                                        if IBAN(i.split("IBAN:")[1]).bic is not None:
                                            podio_data[f"SWIFT {market}"] = IBAN(i.split("IBAN:")[1]).bic.compact
                                elif "Account" in i:
                                    for market in i.split("Account:")[0].split(","):
                                        podio_data[f"Account {market}"] = i.split("Account:")[1]

                elif 'SWIFT' in field:
                    try:
                        if len(podio_data[field]) not in [8, 11]:
                            podio_data[field] = (swift if swift is not None else bic.BIC(podio_data[field]).compact)
                    except Exception:
                        if (podio_data[field].count(";") != podio_data[field].count(":")
                                or podio_data[field].count(";") <= 0):
                            raise ValueError(f'Incorrect {field}')
                        for i in podio_data[field].replace(" ", "").replace("\n", "").split(";"):
                            if i != "":
                                if "SWIFT" in i:
                                    for market in i.split("SWIFT:")[0].split(","):
                                        podio_data[f"SWIFT {market}"] = bic.BIC(i.split("SWIFT:")[1]).compact
                                elif "CODE" in i:
                                    for market in i.split("CODE:")[0].split(","):
                                        podio_data[f"CODE {market}"] = i.split("CODE:")[1]
                                else:
                                    raise ValueError(f'Incorrect {field}')

                elif 'email' in field.lower():
                    if 'Order_Email' in field and len(podio_data[field]) > 1:
                        comment = "The Order Email could be the only one in Podio. Please make a correction."
                        raise ValueError(f'Incorrect {field}')
                    elif "Contact_person_-_emails" in field:
                        for i, x in enumerate(podio_data[field], 1):
                            podio_data[f'{field}{i}'] = x
                        podio_data[field] = ";".join(podio_data[field])
                    elif "Invoicing_Emails" in field:
                        podio_data[field] = ";".join(podio_data[field])
                    else:
                        podio_data[field] = podio_data[field][0]

                elif 'phone' in field:
                    try:
                        podio_data[field] = format_number(parse(podio_data[field]), PhoneNumberFormat.E164)
                    except:
                        podio_data[field] = format_number(parse(podio_data[field], podio_data['Home_Market']),
                                                         PhoneNumberFormat.E164)
                    if podio_data[field] is None:
                        podio_data[field] = ""

                elif 'Markets_to_activate_for_the_partner' in field:
                    create = False
                    for market in podio_data['Markets_to_activate_for_the_partner']:
                        if "All_Shop_IDs" not in podio_data.keys():
                            create = True
                            break
                        elif f"{market}-" not in podio_data['All_Shop_IDs']:
                            create = True
                    if not create:
                        return "There are no new shops to create.", "-", "wrong format"

                elif 'All_Shop_IDs' in field or "pams_partner_id" in field:
                    if "Create core" in data['task_text'] or "Check id's in PAMS" in data['task_text']:
                        podio_data[field] = "" if field not in podio_data else podio_data[field].replace(" ", "")
                        continue
                    else:
                        podio_data[field] = podio_data[field].replace(" ", "")

                elif 'Contact_person' in field:
                    if "Contact_person_2_-_name_&_surname" not in podio_data:
                        if len(podio_data['Contact_person_-_emails']) > 1:
                            podio_data['Contact_person_2_-_name_&_surname'] = podio_data['Contact_person_1_-_name_&_surname']
                        else:
                            podio_data['Contact_person_2_-_name_&_surname'] = ''
                            podio_data['Contact_person_2_position'] = ''

                elif field == "Home_Market" and podio_data['Home_Market'] == "New market":
                    comment = "Can`t create anything when home market is 'New market' contact with " \
                                          "@[Niccolo Coppo](user:5121198) to update country."
                    raise ValueError("There are no required country.")

                elif 'Additional_shipping_locations_-_Sender' in field or 'Return_address' in field:
                    if ('Additional_shipping_locations_-_Sender' in podio_data or 'Return_address' in podio_data) and \
                                        field not in podio_data:
                        continue
                    esentail_keys = ['name', 'street', 'city', 'zipcode', 'countrycode']
                    if 'Return' in field and podio_data['Return_address'].count(";") > 1:
                        comment = "Partner should have only one return address!"
                        print('More than one return addresses')
                        raise ValueError("Incorrect format.")

                    for index, all_address in enumerate(podio_data[field].replace("\n", "").split(";")):
                        if all_address.replace(" ", "") == "":
                            continue

                        key_dict = f"Sender {index}" if 'Sender' in field else f"Return {index}"

                        address_dict, num_address_dict = {}, {}
                        for details in all_address.split("|"):
                            key, value = details.split("=")
                            address_dict[key.lower().replace(" ", "")] = value

                        address_dict['countrycode'] = pycountry.countries.get(alpha_2=address_dict['countrycode']).name
                        address_dict['street_origin'], address_dict['street2'] = "", ""
                        for word in address_dict['street'].replace("\n", " ").split(" "):
                            if len(address_dict['street_origin'] + " " + word) <= 30:
                                address_dict['street_origin'] = address_dict['street_origin'] + " " + word
                            elif len(address_dict['street2'] + " " + word) <= 30:
                                address_dict['street2'] = address_dict['street2'] + " " + word
                        address_dict['street'] = address_dict['street_origin']

                        del address_dict['street_origin']

                        podio_data["shipping_locations"][key_dict] = address_dict

                        # Check if we have all information
                        for key in esentail_keys:
                            if key not in address_dict.keys():
                                comment = "There is an issue with format additional location field. " \
                                                      "Please do the correction."
                                raise ValueError("Incorrect format.")

                elif field in podio_data.keys():
                    continue
                else:
                    print("There is some issue!", "thread_num", podio_data['thread_num'])
                    raise ValueError("There are no required field in dict.")

            except:
                if not comment:
                    comment = f"The field [{field}] is blank or is incorrect, " \
                                          f"please double-check and correct it because it`s an essential field to finish the update."
                return comment, "-", "wrong format"

        if comment_country := False:
            return comment_country, "-", "wrong format"
        else:
            return comment, "", ""


