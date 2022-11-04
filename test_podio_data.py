import phonenumbers
from schwifty import IBAN, bic


def test_data(dict_html, task_dict):
    comment_country = False

    for field in task_dict:
        comment = False

        try:
            if 'Contract' in field or 'RightSignature_contract' in field:
                continue

            elif 'pc_location_name' in field.lower():
                continue

            elif "street" in field.lower():
                dict_html[f'{field} street'] = dict_html[f'{field} street2'] = ""
                for index, word in enumerate(dict_html[field].replace("\n", " ").split(" ")):
                    if len(dict_html[f'{field} street'] + " " + word) <= 33:
                        dict_html[f'{field} street'] = dict_html[f'{field} street'] + " " + word
                    elif len(dict_html[f'{field} street2'] + " " + word) <= 33:
                        dict_html[f'{field} street2'] = dict_html[f'{field} street2'] + " " + word

            elif 'IBAN' in field:
                try:
                    if IBAN(dict_html[field]).bic is not None:
                        swift = IBAN(dict_html[field]).bic.compact
                    dict_html[field] = IBAN(dict_html[field]).compact
                except:
                    try:
                        if dict_html[field].count(";") > 0:
                            dict_html[f"Multiple IBANs"] = True

                            for i in dict_html[field].replace(" ", "").replace("\n", "").split(";"):
                                if i != "":
                                    if "IBAN" in i:
                                        i = i.replace(i.split("IBAN:")[1], IBAN(i.split("IBAN:")[1]).compact)

                                        for market in i.split("IBAN:")[0].split(","):
                                            dict_html[f"IBAN {market}"] = i.split("IBAN:")[1]

                                            if IBAN(i.split("IBAN:")[1]).bic is not None:
                                                dict_html[f"SWIFT {market}"] = IBAN(i.split("IBAN:")[1]).bic.compact
                                    elif "Account" in i:
                                        for market in i.split("Account:")[0].split(","):
                                            dict_html[f"Account {market}"] = i.split("Account:")[1]
                        else:
                            raise ValueError(f'Incorrect {field}')
                    except:
                        comment = f"The field \n[{field}]\n has not proper format please do the correction."
                        raise ValueError(f'Incorrect {field}')

            elif 'SWIFT' in field:
                try:
                    if len(dict_html[field]) not in [8, 11]:
                        if swift != None:
                            dict_html[field] = swift
                        else:
                            dict_html[field] = bic.BIC(dict_html[field]).compact
                except:
                    try:
                        if dict_html[field].count(";") == dict_html[field].count(":") \
                                and dict_html[field].count(";") > 0:
                            for i in dict_html[field].replace(" ", "").replace("\n", "").split(";"):
                                if i != "":
                                    if "SWIFT" in i:
                                        print(f'SWIFT seems to be ok: {bic.BIC(i.split("SWIFT:")[1])}')
                                        for market in i.split("SWIFT:")[0].split(","):
                                            dict_html[f"SWIFT {market}"] = bic.BIC(i.split("SWIFT:")[1]).compact
                                    elif "CODE" in i:
                                        for market in i.split("CODE:")[0].split(","):
                                            dict_html[f"CODE {market}"] = i.split("CODE:")[1]
                                    else:
                                        raise ValueError(f'Incorrect {field}')
                        else:
                            raise ValueError(f'Incorrect {field}')
                    except:
                        comment = f"The field \n[{field}]\n has not proper format please do the correction.\n"
                        raise ValueError(f'Incorrect {field}')

            elif 'Order_Email' in field:
                if dict_html[field].count("@") > 1:
                    comment = "The Order Email could be the only one in Podio. Please make a correction."
                    raise ValueError(f'Incorrect {field}')

            elif 'phone' in field:
                try:
                    dict_html[field] = phonenumbers.format_number(phonenumbers.parse(dict_html[field]),
                                                                  phonenumbers.PhoneNumberFormat.E164)
                except:
                    dict_html[field] = phonenumbers.format_number(phonenumbers.parse(dict_html[field],
                                                                                     dict_html['Home_Market']),
                                                                  phonenumbers.PhoneNumberFormat.E164)

            elif 'Legal_Name' in field:
                if not field in dict_html.keys():
                    dict_html[field] = ''

            elif 'Transfer_price_restriction' in field:
                if not field in dict_html.keys():
                    dict_html[field] = 50

            elif 'Markets_to_activate_for_the_partner' in field:
                create = False
                for market in dict_html['Markets_to_activate_for_the_partner']:
                    if "All_Shop_IDs" not in dict_html.keys():
                        create = True
                        break
                    elif f"{market}-" not in dict_html['All_Shop_IDs']:
                        create = True
                if not create:
                    return f"There are no new shops to create.", "-", "wrong format", dict_html

            elif 'Contact_person_2' in field:
                if not field in dict_html.keys():
                    dict_html[field] = ''

            elif 'All_Shop_IDs' in field:
                if "Date_of_signing" in task_dict:
                    dict_html['All_Shop_IDs'] = ""
                    continue
                else:
                    dict_html[field] = dict_html[field].replace(" ", "")

            elif field == "Home_Market" and dict_html['Home_Market'] == "New market":
                comment = "Can`t create anything when home market is 'New market' contact with " \
                          "@[Niccolo Coppo](user:5121198) to update country."
                raise ValueError("There are no required country.")

            elif 'Full_Commission_From_Contract' in field:
                continue

            elif 'Additional_shipping_locations_-_Sender' in field or 'Return_address' in field:
                if ('Additional_shipping' in dict_html.keys() or 'Return_address' in dict_html.keys()) and \
                        field not in dict_html.keys():
                    continue

                esentail_keys = ['name', 'street', 'city', 'zipcode', 'countrycode']
                if 'Return' in field and dict_html['Return_address'].count(";") > 1:
                    comment = "Partner should have only one return address!"
                    print('More than one return addresss')
                    raise ValueError("Incorrect format.")

                dict_html["shipping_locations"] = {}
                for index, all_address in enumerate(dict_html[field].replace("\n", "").split(";")):
                    if all_address.replace("\n", "").replace(" ", "") == "":
                        continue

                    if 'Sender' in field:
                        key_dict = f"Sender {index}"
                    elif 'Return' in field:
                        key_dict = f"Return {index}"

                    address_dict, num_address_dict = {}, {}
                    for details in all_address.split("|"):
                        key, value = details.split("=")
                        address_dict[key.lower().replace(" ", "")] = value

                    address_dict['street_origin'] = address_dict['street2'] = ""
                    for index, word in enumerate(address_dict['street'].replace("\n", " ").split(" ")):
                        if len(address_dict['street_origin'] + " " + word) <= 33:
                            address_dict['street_origin'] = address_dict['street_origin'] + " " + word
                        elif len(address_dict['street2'] + " " + word) <= 33:
                            address_dict['street2'] = address_dict['street2'] + " " + word
                    else:
                        address_dict['street'] = address_dict['street_origin']

                    del address_dict['street_origin']

                    dict_html["shipping_locations"][key_dict] = address_dict

                    # Check if we have all information
                    for key in esentail_keys:
                        if key not in address_dict.keys():
                            comment = "There is an issue with format additional location field. Please do the correction."
                            raise ValueError("Incorrect format.")
            else:
                if field in dict_html.keys():
                    continue
                else:
                    print("There is some issue!", "thread_num", dict_html['thread_num'])
                    raise ValueError("There are no required field in dict.")

        except:
            if not comment:
                comment = f"The field [{field}] is blank or is incorrect, " \
                          f"please double-check and correct it because it`s an essential field to finish the update."
            return comment, "-", "wrong format", dict_html

    else:
        if comment_country:
            return comment_country, "-", "wrong format", dict_html
        else:
            return comment, "", "", dict_html
