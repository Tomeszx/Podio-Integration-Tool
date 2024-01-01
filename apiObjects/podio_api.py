import pandas as pd
import warnings
import re

from bs4 import MarkupResemblesLocatorWarning, BeautifulSoup as bS
from datetime import datetime
from difflib import SequenceMatcher
from functools import partial
from multiprocessing import Pool
from apiObjects.google_sheet_api import send_data
from requests import request
from result import Ok, Err, Result


class Podio:
    def __init__(self, access_tokens: list, credentials: dict):
        self.access_tokens = access_tokens
        self.credentials = credentials
        self.limit = None
        self.remaining = None

    def get_access_token(self, client_id: str, client_secret: str) -> str:
        data = {
            'grant_type': 'password',
            'client_id': client_id,
            'client_secret': client_secret,
            'username': self.credentials['username_podio'],
            'password': self.credentials['password_podio']
        }

        response = request('post', 'https://podio.com/oauth/token', data=data)
        if response.status_code != 200:
            raise ConnectionRefusedError(data["error_description"])

        return response.json()['access_token']

    def _check_api_limit(self) -> None:
        if (self.limit - self.remaining) / self.limit >= 0.80:
            try:
                self.access_tokens.pop(0)
            except IndexError as e:
                raise ConnectionRefusedError("You have almost exceed the rate limit. Try again for one hour.") from e

    def _send_request(self, method: str, endpoint: str, data=None, params=None) -> dict:
        url = f"https://api.podio.com/{endpoint}"
        headers = {'Authorization': f'Bearer {self.access_tokens[0]}'}
        response = request(method, url, headers=headers, json=data, params=params)

        self.limit = int(response.headers.get('X-Rate-Limit-Limit'))
        self.remaining = int(response.headers.get('X-Rate-Limit-Remaining'))

        if response.status_code == 200:
            return response.json()
        return {}

    def _delete_task(self, task_id: str) -> dict:
        return self._send_request(method='delete', endpoint=f'task/{task_id}')

    def _search_for_user(self, user_name: str) -> str:
        params = {'query': user_name, 'ref_type': 'profile', 'limit': 2}
        response = self._send_request('get', 'search/v2', params=params)

        for user in response['results']:
            if user_name == user['title']:
                return f"{user['link']}".split('/')[-1]
        return ""

    def _get_tasks(self, responsible_id: str = '6461478') -> list:
        tasks_summary = self._send_request('GET', 'task/total/')['own']
        print(f"{'':^60}", f" Tasks done yesterday -> {tasks_summary['completed_yesterday']}\n")

        with Pool() as pool:
            results = []
            for offset in range(0, tasks_summary['later'], 100):
                params = {'responsible': responsible_id, 'completed': False, 'offset': offset, 'limit': 100}
                result = pool.apply_async(self._send_request, ('GET', 'task/', None, params))
                results.append(result)

            flat_results = []
            for result in results:
                flat_results.extend(result.get())
            return flat_results

    @staticmethod
    def _find_tasks(task_key: str, task_title: str) -> bool:
        return task_key in task_title

    @staticmethod
    def _map_tasks(task: dict, task_to_do: str):
        return {
            'task_id': task['task_id'],
            'task_text': task['text'],
            'shop_item_id': task['ref']['data']['item_id'],
            'partner_name': task['ref']['data']['title'],
            'part_title': task_to_do,
            'partner_type': task['ref']['data']['app']['config']['name'].lower(),
            'link_to_shop': task['ref']['data']['link'],
            'task_requester': task['description']
        }

    def prepare_tasks(self, tasks_dict: dict) -> list[dict]:
        tasks_list = {}
        all_tasks = self._get_tasks()
        for task in all_tasks:
            if not task:
                continue

            func_part = partial(self._find_tasks, task_title=task['text'])
            full_title = f"{task['ref']['data']['title']} {task['text']}"

            if "PAMS TEST" not in task['ref']['data']['title']:
                continue
            if full_title in tasks_list:
                print('Deleting task:', full_title)
                self._delete_task(task['task_id'])
            elif task_to_do := list(filter(func_part, tasks_dict)):
                tasks_list[full_title] = self._map_tasks(task, task_to_do[0])

        print(f'{"":_^110}\n\n', f"{'':^60}", f"Number of tasks in Podio -> {len(all_tasks)}")
        print(f"{'':^60}", " Tasks for the BOT ->", len(tasks_list), f"\n{'':_^110}\n\n")
        return list(tasks_list.values())

    def update_field(self, field_id: str, value: str, item_id: int) -> dict:
        return self._send_request('put', f'item/{item_id}/value/{field_id}', data={"value": value})

    @staticmethod
    def _map_field(field: dict) -> list | str:
        if field['type'] == 'category':
            if field['config']['settings']['multiple'] is True:
                return [details['value']['text'] for details in field['values']]
            return field['values'][0]['value']['text']
        elif field['type'] in ['text', 'number', 'phone', 'calculation']:
            field_value = field['values'][0]['value']
            return bS(field_value, 'html.parser').get_text().replace("\xa0", " ")
        elif field['type'] in ['contact', 'email']:
            return [details['value'] for details in field['values']]
        elif field['type'] == 'date':
            return [datetime.strptime(value['start_date'], "%Y-%m-%d") for value in field['values']]

    def get_partner_details(self, item_id: int) -> dict[str, any]:
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)

        response = self._send_request(method='get', endpoint=f'item/{item_id}')
        data = {
            "fields_ids": {}, 'comments': [], 'partner_type': response['app']['name'], 'partner_name': response['title']
        }
        for field in response['fields']:
            key = field['label'].strip().replace(" ", "_")
            data[key] = self._map_field(field)
            data["fields_ids"][key] = field['field_id']

        for comment in response['comments']:
            if comment['created_by']["name"] == "Update Admins":
                data['comments'].append({'date': comment['created_on'], 'value': comment['value']})

        for files in response['files']:
            data['files'] = ".pdf" in files["name"] or ".PDF" in files["name"]

        return data

    def prepare_data(self, data: dict, task: dict, tasks_fields: dict) -> Result[dict, str]:
        self._check_api_limit()

        for field in tasks_fields[task['part_title']]:
            if not data.get(field):
                return Err(f'The {field} field is empty in Podio. Please fill out this field.')
        if "Create core" in task['part_title']:
            if not data.get('files'):
                return Err("PDF contract is not attached to the Podio.")
            elif not data.get('Password'):
                data['Username'], data['Password'] = self.add_username_password(data, task)

        return Ok(data)

    def add_username_password(self, data: dict, task: dict) -> tuple[str, str]:
        fields_ids = ["188759350", "188759351"]
        if task['partner_type'] == "brands":
            fields_ids = ['222617769', '193610265']

        d = data['Date_of_signing'][0]
        v = data['VAT_TAX_Number']
        password = str(d.day).zfill(2) + str(d.month).zfill(2) + 'Success.' + v[-2:]

        self.update_field(fields_ids[0], data['Order_Email'], task['shop_item_id'])
        self.update_field(fields_ids[1], password, task['shop_item_id'])

        return data['Order_Email'], password

    def add_ids(self, new_ids: list, pams_id: str, task: dict) -> None:
        if pams_id:
            pams_id_field = {'brands': '251071111', 'partners': '249863352'}
            self.update_field(pams_id_field[task['partner_type']], pams_id, task['shop_item_id'])

        all_shop_id_field = {'brands': '193610233', 'partners': '187361639'}
        string_ids = ','.join(list(dict.fromkeys(new_ids)))
        self.update_field(all_shop_id_field[task['partner_type']], string_ids, task['shop_item_id'])

    def complete_task(self, task_id: int, complete_action: bool = True) -> dict:
        return self._send_request(method='put', endpoint=f'task/{task_id}', data={"completed": complete_action})

    def add_comment(self, value: str, task: dict) -> str:
        user = ''
        if task["task_requester"]:
            user = f'(user:{self._search_for_user(task["task_requester"])})'
        msg = f"@[{task['task_requester']}]{user}\n\n{value}"

        array = [[task["partner_name"], task['part_title'], value, task["link_to_shop"], datetime.now()]]
        pandas_array = pd.DataFrame(array)
        send_data(col=1, sheet_name="Bot msgs", data=pandas_array)

        return self._send_request(
            'post', f'comment/item/{task["shop_item_id"]}/', data={"value": msg}
        )['rich_value']

    def add_error_comment(self, comment: str, task: dict, data: dict, comment_frequency: int) -> str:
        check = re.sub('[^a-zA-Z0-9]', '', comment).lower()

        for podio_comment in data['comments'][::-1]:
            comm_date = datetime.strptime(podio_comment["date"].split()[0], "%Y-%m-%d").date()
            com_value = re.sub('[^a-zA-Z0-9]', '', "".join(podio_comment['value'].split("\n")[1:])).lower()

            if (datetime.now().date() - comm_date).days > comment_frequency:
                continue
            elif check in com_value:
                return 'Comment not added. (Duplicate).'
            elif SequenceMatcher(None, check, com_value).ratio() > 0.9:
                return 'Comment not added. (Duplicate).'
        return self.add_comment(comment, task).replace("\n\n", "\n")
