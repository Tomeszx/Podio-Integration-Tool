import json

from gooey import Gooey, GooeyParser


@Gooey(
        program_name="Podio Integration tool",
        program_description="This tool is used to scrape Podio updates and moves them into other services",
        terminal_font_color='#FFFFFF',
        terminal_panel_color='#222222',
        body_bg_color='#23395d',
        header_bg_color='#23395d',
        footer_bg_color='#23395d',
        sidebar_bg_color='#23395d',
        progress_regex=r"\[(\d+)/(\d+)\]",
        progress_expr="x[0] / x[1] * 100",
        disable_progress_bar_animation=True,
        default_size=(910, 720),
        timing_options={'show_time_remaining': True, 'hide_time_remaining_on_complete': False},
        tabbed_groups=True,
    )
class GUI:
    def __init__(self):
        self.tasks = json.load(open("additional_files/tasks.json"))
        self.login_default = json.load(open("credentials/config.json"))

    def login_tab(self, parser):
        user = self.login_default['Update Admins']
        log_det = parser.add_argument_group("Login details")

        for service in ['podio', 'pams']:
            log_det.add_argument(
                f"--username_{service}",
                metavar=f'Username {service}',
                default=user[f'username_{service}']
            )
            log_det.add_argument(
                f"--password_{service}",
                metavar=f'Password {service}',
                default=user[f'password_{service}'],
                widget='PasswordField'
            )

    def api_keys_tab(self, parser):
        user = self.login_default['Update Admins']
        api_det = parser.add_argument_group("Podio Api Keys")

        for i in range(1, 6):
            api_det.add_argument(
                f"--client_id{i}",
                metavar='Client ID Podio',
                default=user[f'client_id{i}']
            )
            api_det.add_argument(
                f"--client_secret{i}",
                metavar='Client Secret Podio',
                widget='PasswordField',
                default=user[f'client_secret{i}']
            )

    @staticmethod
    def additional_options_tab(parser):
        gen_opt = parser.add_argument_group("General options")

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
        gen_opt.add_argument("--comment_frequency",
                             metavar=" After [X] days I should add the same comment?",
                             widget="Slider",
                             default=4,
                             gooey_options={'min': 0, 'max': 10}, type=int)

    @staticmethod
    def tasks_options_tab(parser, tasks):
        checkboxes = parser.add_argument_group("Detailed tasks")

        for task_key in tasks.keys():
            checkboxes.add_argument(
                f"--{task_key.replace(' ', '_')}",
                metavar=' ',
                widget="BlockCheckbox",
                default=False,
                action='store_true',
                gooey_options={'checkbox_label': f" {task_key.replace(' ', '_')}", 'show_label': True}
            )

    def handle(self) -> dict:
        parser = GooeyParser()
        self.additional_options_tab(parser)
        self.tasks_options_tab(parser, self.tasks)
        self.login_tab(parser)
        self.api_keys_tab(parser)

        return vars(parser.parse_args())
