import random
import os

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from apiObjects.podio_api import Podio
from task_manager import TasksManager
from interface import GUI


def get_tasks(user_inputs: dict, chosen_tasks: dict):
    if user_inputs['All_tasks']:
        return {
            task_key.replace("_", " "): chosen_tasks[task_key.replace("_", " ")]
            for task_key, value in user_inputs.items()
            if task_key.replace("_", " ") in chosen_tasks and value
        }
    return chosen_tasks


def setup_chromedriver_options(user_inputs: dict) -> ChromeOptions:
    chrome_options = ChromeOptions()

    if not user_inputs["headless_website"]:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.page_load_strategy = "eager"

    prefs = {"profile.default_content_settings.popups": 2, "download.default_directory": os.getcwd()}
    chrome_options.add_experimental_option("prefs", prefs)

    return chrome_options


def collect_tasks(user_inputs: dict) -> tuple:
    podio = Podio([], {})
    access_tokens = []
    for i in random.sample(range(1, 6), 5):
        token = podio.get_access_token(user_inputs[f'client_id{i}'], user_inputs[f'client_secret{i}'])
        access_tokens.append(token)

    podio.access_tokens = access_tokens
    return podio.prepare_tasks(chosen_tasks), access_tokens


def run(user_inputs: dict, chosen_tasks: dict):
    tasks_array, access_tokens = collect_tasks(user_inputs)

    options = setup_chromedriver_options(user_inputs)
    driver = Chrome(options=options, service=ChromeService())

    manager = TasksManager(user_inputs['comment_frequency'], access_tokens, user_inputs, options, driver)
    manager.perform_data(tasks_array, chosen_tasks)


if __name__ == "__main__":
    gui = GUI()
    user_inputs = gui.handle()
    chosen_tasks = get_tasks(user_inputs, chosen_tasks=gui.tasks)
    run(user_inputs, chosen_tasks)
