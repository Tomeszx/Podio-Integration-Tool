from functools import partial

from apiObjects.podio_api import Podio
from pageObjects.base_methods import BaseMethods
from selenium.webdriver.chrome.webdriver import WebDriver
from result import Ok, Err, Result, is_ok, is_err

from pageObjects.pams.create_view_page import CreateViewPage
from pageObjects.pams.edit_view_page import EditViewPage
from pageObjects.pams.info_view_page import InfoViewPage


class PageManager(BaseMethods):

    def __init__(self, driver: WebDriver, user_inputs: dict, podio: Podio):
        super().__init__(driver)
        self.user_inputs = user_inputs
        self.podio = podio
        self.info_page = partial(InfoViewPage, self.driver)
        self.edit_page = partial(EditViewPage, self.driver)
        self.create_page = partial(CreateViewPage, self.driver)

    @staticmethod
    def _get_list_elem_as_first(origin_list: list, elem_to_move, post_index: int) -> None:
        for elem in origin_list:
            if elem in elem_to_move:
                elem_to_move = origin_list.pop(origin_list.index(elem))
                return origin_list.insert(post_index, elem_to_move)

    def _sort_core_market_as_first(self, all_shop_ids: list[str], home_market: str) -> list[str]:
        prefix_list = {shop_id.split("-")[0] for shop_id in all_shop_ids}

        if home_market.upper() in {'DK', 'SE', 'NL', 'BE', 'PL', 'CH', 'NO'} and home_market.upper() in prefix_list:
            self._get_list_elem_as_first(all_shop_ids, home_market, 0)
        elif "NL" in prefix_list:
            self._get_list_elem_as_first(all_shop_ids, 'NL', 0)
        else:
            markets_succession = {"DK", "BE", "NO", "SE"}
            core_priority = next((market for market in markets_succession if market in prefix_list), None)
            self._get_list_elem_as_first(all_shop_ids, core_priority[0], 0)
        return all_shop_ids

    def _convert_shop_ids(self, podio_data: dict, task_part_title: str) -> str:
        if task_part_title not in ["Other markets", "Create core"]:
            return podio_data.get('All_Shop_IDs', "")

        all_shop_ids = []
        for market in podio_data['Markets_to_activate_for_the_partner']:
            if f"{market}-" not in podio_data.get('All_Shop_IDs', ''):
                all_shop_ids.append(f'{market}-create')

        if "Create core" in task_part_title and len(all_shop_ids) > 0:
            return ",".join(self._sort_core_market_as_first(all_shop_ids, podio_data['Home_Market']))
        return ','.join(all_shop_ids)

    def _manage_update_after_creating_markets(self, data: dict, shop_ids: list, task: dict) -> Result[None, str]:
        result = self.info_page(data, shop_ids[-1].split('-')[0]).wait_for_ids(shop_ids)
        if data.get('All_Shop_IDs', '') == '':
            all_shop_ids = self._sort_core_market_as_first(result.value[1], data['Home_Market'])
        else:
            all_shop_ids = data.get('All_Shop_IDs', '').split(",") + result.value[1]

        self.podio.add_ids(all_shop_ids, data['pams_partner_id'], task)

        if is_err(result):
            return Err(f'\n\n{result.value[0]}')
        return Ok(None)

    @staticmethod
    def _get_comment_from_output(error_comments: dict, success_comments: dict) -> Result[str, str]:
        comment = ""
        for comment_to_add, markets in success_comments.items():
            comment += f"# The msg from markets [{', '.join(markets)}]:\n{comment_to_add}\n\n"
            if not comment_to_add:
                comment += "Nothing was changed. Data in PaMS are the same.\n\n"
        if error_comments:
            for error_comment, markets in error_comments.items():
                comment += f"\n\n# The msg from markets [{', '.join(markets)}]\n{error_comment}"
            return Err(comment)
        return Ok(comment)

    def _process_output(self, results: list) -> Result[str, str]:
        error_comments, success_comments = {}, {}
        for result in results:
            try:
                if is_err(result[1]) and result[1].value not in error_comments:
                    error_comments[result[1].value] = [result[0]]
                elif is_err(result[1]):
                    error_comments[result[1].value].append(result[0])
                elif result[1].value not in success_comments:
                    success_comments[result[1].value] = [result[0]]
                else:
                    success_comments[result[1].value].append(result[0])
            except AttributeError as e:
                raise AttributeError(f'{type(result)=} {result=}') from e
        return self._get_comment_from_output(error_comments, success_comments)

    def _open_specific_market(self, market: str):
        converted_market = market.replace('UK', 'GB').replace('SHWRM', 'PL')
        self.wait_for_clickability(EditViewPage.market_selector.__format__(converted_market.upper())).click()
        self.wait_for(only_readystate=True)

        if add_market := self.get_elements(CreateViewPage.add_market_button):
            add_market[0].click()
        elif edit_market := self.get_elements(EditViewPage.edit_market_button):
            edit_market[0].click()

    def _process_multiple_markets_update(self, func, all_shop_ids: list, podio_data: dict) -> Result[str, str]:
        self.open(f"/preview/{podio_data['pams_partner_id']}/info")

        results = []
        for full_shop_id in all_shop_ids:
            market = full_shop_id.split('-')[0]
            self._open_specific_market(market)

            edit_page = self.edit_page(podio_data, market)
            values_before = edit_page.get_all_values(self.driver.current_url)
            result = func(self=edit_page)

            if type(result) is list and all(is_ok(res) for res in result):
                save_result = edit_page.save(values_before)
                results.append((market, save_result))
            elif type(result) is not list and is_ok(result):
                save_result = edit_page.save(values_before)
                results.append((market, save_result))
            elif type(result) is list:
                results.extend((market, res) for res in result if is_err(res))
            else:
                results.append((market, result))
        return self._process_output(results)

    def _create_core_market(self, data: dict, market: str, task: dict) -> Result[None, str]:
        if not data.get('pams_partner_id', ''):
            self.open('/create/info')
            result = self.info_page(data, market).add_location_info_and_go_to_next_step()
            if is_err(result):
                return result

            data['pams_partner_id'] = self.driver.current_url.split("/")[5]
            self.podio.add_ids([], data['pams_partner_id'], task)
        else:
            self.open(f"/preview/{data['pams_partner_id']}/info")
            self._open_specific_market(market)

        create_page = self.create_page(data, market)
        results = create_page.update_all_fields_in_create_view()

        if errors := [(market, result) for result in results if is_err(result)]:
            return self._process_output(errors)
        output = [(market, create_page.save_create_view({}))]
        return self._process_output(output)

    def run(self, func, data: dict, task: dict) -> Result:
        origin_shop_ids = self._convert_shop_ids(data, task['part_title']).split(',')
        used_shop_ids = origin_shop_ids.copy()

        if 'CreateViewPage' in func.__qualname__:
            create_result = self._create_core_market(data, market=used_shop_ids.pop(0).split('-')[0], task=task)
            if is_err(create_result):
                return create_result
            func = EditViewPage.update_all_fields_in_edit_view

        result = self._process_multiple_markets_update(func, used_shop_ids, data)

        if task['part_title'] in {"Create core", "Other markets"}:
            update_after_create = self._manage_update_after_creating_markets(data, origin_shop_ids, task)
            if is_err(update_after_create):
                return Err(f'{result.err_value or ""}\n\n{update_after_create.err_value}')
        if 'CreateViewPage' in func.__qualname__:
            return Ok(f'{create_result.ok_value}\n\n{result.ok_value}')
        return result
