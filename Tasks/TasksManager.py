#!venv/bin/python3.9
from Services.Podio import Podio
from Services.Admin import Admin
from Services.PaMS import PaMS
from Services.ProductService import ProductService


class TasksManager:
    def __init__(self, comment_period: int, credentials: dict, access_tokens: list):
        self.comment_period = comment_period
        self.credentials = credentials
        self.access_tokens = access_tokens

    def perform_data(self, website, tasks_list: dict, tasks_dict: dict):
        for task_row in tasks_list:
            data = {"tasks_keys": tasks_dict, 'comment_period': self.comment_period}
            data |= task_row

            if "vintage" in data['partner_type']:
                data['partner_type'] = "partners"

            print(f"\n{'':^40}>>>>>>>> {data['Partner_Name']} {data['task_text']} <<<<<<<<<<")

            podio = Podio(data, self.access_tokens, self.credentials)
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

            self.manage_tasks(website, podio, data)

    def manage_tasks(self, website, podio, data: dict) -> None:
        if 'pc location' in data['part_title'].lower():
            ProductService(self.credentials).create_pc_location(website, data)
            action, comment = ProductService(self.credentials).add_aliases(website, data)

        elif 'add aliases' in data['part_title'].lower():
            action, comment = ProductService(self.credentials).add_aliases(website, data)

        else:
            action, comment = self.admin_tasks(website, podio, data)

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

    def admin_tasks(self, website, podio, data: dict) -> (str, str):
        data['all_used_ids'] = self.convert_shop_ids(podio, data)
        pams, admin = PaMS(self.credentials), Admin(self.credentials)

        for shop_id in data['all_used_ids'].split(","):
            data['market'] = shop_id.split("-")[0]
            data['id'] = shop_id.split("-")[1]

            if "Check id's in PaMS" in data['part_title']:
                pams.open(website, data["pams_partner_id"])
                data['pams_id'] = data["pams_partner_id"]
                new_ids, action, comment = pams.wait_for_ids(website, data)
                podio.add_new_shop_ids(new_ids, data['pams_id'])
                action = "Success"
                if "Issue" in comment:
                    action = "Issue"
                break

            elif 'Additional shipping locations' in data['part_title']:
                action, comment = pams.update_extra_shipp_address(website, data)

            elif 'Return address' in data['part_title']:
                data |= data["shipping_locations"]["Return 0"]
                action, comment = pams.update_edit_view(website, data)

            elif "commission" in data['part_title'].lower().replace(" ", ""):
                if data['market'] == "CN":
                    continue
                if data.get('commission_values') is None:
                    data['commission_values'] = []
                action, comment = admin.update_commission(website, data)

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

                action, comment = pams.update_edit_view(website, data)

                if "Issue" in action:
                    if "Create core" in data['part_title']:
                        podio.add_new_shop_ids([], data['pams_id'])
                    return "Issue", comment
                elif "Create core" in data['part_title'] and shop_id == data['all_used_ids'].split(",")[-1]:
                    new_ids, action, err_comment = pams.wait_for_ids(website, data)
                    podio.add_new_shop_ids(new_ids, data['pams_id'])
                    if err_comment:
                        return "Issue", err_comment
                elif "other market" in data['part_title'].lower() and shop_id == data['all_used_ids'].split(",")[-1]:
                    new_ids, action, err_comment = pams.wait_for_ids(website, data)
                    podio.add_new_shop_ids(new_ids, data['pams_id'])
                    if err_comment:
                        return "Issue", err_comment
            else:
                action, comment = pams.update_edit_view(website, data)

            if "Issue" in action or "error" in comment:
                return action, comment

        return action, comment

    def convert_shop_ids(self, podio, data: dict):
        if data['part_title'] in ["Check id's in PaMS", "Other markets", "Create core"]:
            all_shop_ids = ""
            for i in data['Markets_to_activate_for_the_partner']:
                if f"{i}-" not in data['All_Shop_IDs']:
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

        return all_shop_ids