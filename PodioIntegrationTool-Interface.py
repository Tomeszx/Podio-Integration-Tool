import random
import json
import os
import threading

from gooey import Gooey, GooeyParser
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService

from Services.Podio import Podio
from Tasks.TasksManager import TasksManager

login_default = json.load(open("Credentials/config.json"))


class GUI:
    chromedriver_options = None
    credentials = {}

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

        log_det.add_argument("--username_podio",
                             metavar='Username Podio',
                             default=user['username_podio'])
        log_det.add_argument("--password_podio",
                             metavar='Password Podio',
                             widget='PasswordField',
                             default=user['password_podio'])

        log_det.add_argument("--username_admin",
                             metavar='Username Admin',
                             default=user['username_admin'])
        log_det.add_argument("--password_admin",
                             metavar='Password Admin',
                             widget='PasswordField',
                             default=user['password_admin'])

        log_det.add_argument("--username_pc",
                             metavar='Username Product Service',
                             default=user['username_pc'])
        log_det.add_argument("--password_pc",
                             metavar='Password Product Service',
                             widget='PasswordField',
                             default=user['password_pc'])

        log_det.add_argument("--username_pams", metavar='Username Partner Management System',
                            default=user['username_pams'])
        log_det.add_argument("--password_pams",
                             metavar='Password Partner Management System',
                             widget='PasswordField',
                             default=user['password_pams'])

    def api_keys_card(self, parser):
        user = login_default['Update Admins']
        api_det = parser.add_argument_group("Podio Api Keys")

        api_det.add_argument("--client_id1",
                             metavar='Client ID Podio',
                             default=user['client_id_podio1'])
        api_det.add_argument("--client_secret1",
                             metavar='Client Secret Podio',
                             widget='PasswordField',
                             default=user['client_secret_podio1'])

        api_det.add_argument("--client_id2",
                             metavar='Client ID Podio',
                             default=user['client_id_podio2'])
        api_det.add_argument("--client_secret2",
                             metavar='Client Secret Podio',
                             widget='PasswordField',
                             default=user['client_secret_podio2'])

        api_det.add_argument("--client_id3",
                             metavar='Client ID Podio',
                             default=user['client_id_podio3'])
        api_det.add_argument("--client_secret3",
                             metavar='Client Secret Podio',
                             widget='PasswordField',
                             default=user['client_secret_podio3'])

        api_det.add_argument("--client_id4",
                             metavar='Client ID Podio',
                             default=user['client_id_podio4'])
        api_det.add_argument("--client_secret4",
                             metavar='Client Secret Podio',
                             widget='PasswordField',
                             default=user['client_secret_podio4'])

        api_det.add_argument("--client_id5",
                             metavar='Client ID Podio',
                             default=user['client_id_podio5'])
        api_det.add_argument("--client_secret5",
                             metavar='Client Secret Podio',
                             widget='PasswordField',
                             default=user['client_secret_podio5'])

    def options_card(self, parser):
        gen_opt = parser.add_argument_group("General options")

        gen_opt.add_argument("--threads_num",
                             metavar=" How many threads do you need?",
                             widget="Slider",
                             gooey_options={'min': 1, 'max': 6}, type=int)
        gen_opt.add_argument("--comment_period",
                             metavar=" After [X] days I should add the same comment?",
                             widget="Slider",
                             default=4,
                             gooey_options={'min': 1, 'max': 10}, type=int)

        gen_opt.add_argument("--headless_website",
                             metavar=" ",
                             widget="BlockCheckbox",
                             default=True,
                             action='store_false',
                             gooey_options={'checkbox_label': " headless website", 'show_label': True})
        gen_opt.add_argument("--All_tasks",
                             metavar=" ",
                             widget="BlockCheckbox",
                             default=True,
                             action='store_false',
                             gooey_options={'checkbox_label': " All tasks except 'Add commission'", 'show_label': True})

    def tasks_options_card(self, parser, tasks):
        checkboxes = parser.add_argument_group("Detailed tasks")

        for task_key in tasks.keys():
            checkboxes.add_argument(f"--{task_key.replace(' ', '_')}",
                                    metavar=' ',
                                    widget="BlockCheckbox",
                                    default=False,
                                    action='store_true',
                                    gooey_options={
                                        'checkbox_label': f" {task_key.replace(' ', '_')}",
                                        'show_label': True
                                    })

    def handle(self):
        tasks = json.load(open("Tasks/Tasks.json"))

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

        self.credentials.update(user_inputs)

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
        access_tokens = [Podio({}, [], self.credentials).__get_access_token__(
            user_inputs[f'client_id{i}'], user_inputs[f'client_secret{i}']) for i in random.sample(range(1, 6), 5)]
        tasks_list = Podio({}, access_tokens, self.credentials).get_tasks(tasks_dict)

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
            task_manager = TasksManager(comment_period, self.credentials, access_tokens)
            x = threading.Thread(target=task_manager.perform_data,
                                 args=(website1, tasks_list[start_index:end_index], tasks_dict))
            threads.append(x)
            x.start()

        for thread in threads:
            thread.join()


if __name__ == "__main__":
    gui = GUI()
    gui.handle()
