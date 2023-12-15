import json
import pandas as pd
import datetime as dt
from datetime import timedelta
import difflib
from typing import Dict
from cryptography.fernet import Fernet

from mindsdb.integrations.handlers.frappe_handler.frappe_tables import FrappeDocumentsTable
from mindsdb.integrations.handlers.frappe_handler.frappe_client import FrappeClient
from mindsdb.integrations.libs.api_handler import APIHandler
from mindsdb.integrations.libs.response import (
    HandlerStatusResponse as StatusResponse,
    HandlerResponse as Response,
)
from mindsdb.utilities import log
from mindsdb_sql import parse_sql
from six import string_types
from langchain.tools import Tool

logger = log.getLogger(__name__)

class FrappeHandler(APIHandler):
    """A class for handling connections and interactions with the Frappe API.

    Attributes:
        client (FrappeClient): The `FrappeClient` object for interacting with the Frappe API.
        is_connected (bool): Whether or not the API client is connected to Frappe.
        domain (str): Frappe domain to send API requests to.
        access_token (str): OAuth token to use for authentication.
    """

    # Declaring class-level constants
    SALES_QUOTATION = 'Quotation'
    SALES_INVOICE = 'Sales Invoice'
    SALES_ORDER = 'Sales Order'

    def __init__(self, name: str = None, **kwargs):
        """Registers all API tables and prepares the handler for an API connection.

        Args:
            name: (str): The handler name to use
        """
        super().__init__(name)
        self.client = None
        self.is_connected = False

        args = kwargs.get('connection_data', {})
        if not args:
            return
        self.access_token = args['access_token']
        self.domain = args['domain']

        document_data = FrappeDocumentsTable(self)
        self._register_table('documents', document_data)
        self.connection_data = args
        self.erp_url = 'https://cloude8-v13beta-demo.cloude8.com'

    def back_office_config(self):
        tools = {
            'get_company': 'have to be used by assistant to get all permitted companies for the user. Input is None',
            'check_company_exists': 'useful to check the company is exist using fuzzy search. Input is company',
            'register_new_customer': 'have to be used by assistant to register a new customer. Input is JSON object serialized as a string.',
            'create_sales_quotation': 'have to be used by assistant to register a sales invoice. Input is JSON object serialized as a string',
            'create_sales_invoice': 'have to be used by assistant to register a sales invoice. Input is JSON object serialized as a string',
            'create_sales_order': 'have to be used by assistant to register a sales order. Input is JSON object serialized as a string.',
            'submit_sales_quotation': 'have to be used by assistant to submit a quotation. Input is JSON object serialized as a string.',
            'submit_sales_invoice': 'have to be used by assistant to submit a sales invoice. Input is JSON object serialized as a string.',
            'submit_sales_order': 'have to be used by assistant to submit a sales order. Input is JSON object serialized as a string.',
            'update_sales_quotation': 'have to be used by assistant to update a sales quotation. Input is JSON object serialized as a string.',
            'update_sales_invoice': 'have to be used by assistant to update a sales invoice. Input is JSON object serialized as a string.',
            'update_sales_order': 'have to be used by assistant to update a sales order. Input is JSON object serialized as a string.',
            'cancel_sales_quotation': 'have to be used by assistant to cancel a sales quotation. Input is JSON object serialized as a string.',
            'cancel_sales_invoice': 'have to be used by assistant to cancel a sales invoice. Input is JSON object serialized as a string.',
            'cancel_sales_order': 'have to be used by assistant to cancel a sales order. Input is JSON object serialized as a string.',
            'register_payment_entry': 'have to be used by assistant to create a payment entry. Input is JSON object serialized as a string.',
            'get_sales_quotation_detail': 'have to be used by asssitant to get the sales quotation details. Input is sales quotation name',
            'get_sales_invoice_detail': 'have to be used by asssitant to get the sales invoice details. Input is sales invoice name',
            'get_sales_order_detail': 'have to be used by asssitant to get the sales order details. Input is sales order name',
            'get_sales_quotation_pdf': 'have to be used by assistant to get the pdf url for the sales quotation. Input is sales quotation name',
            'get_sales_invoice_pdf': 'have to be used by assistant to get the pdf url for the sales invoice. Input is sales invoice name',
            'get_sales_order_pdf': 'have to be used by assistant to get the pdf url for the sales order. Input is sales order name',
            'check_customer_exists': 'useful to check the company exists using fuzzy search. Input is customer',
            'search_customer_by_name': 'have to be used by assistant to find customer based on provided name. Input it customer name',
            'check_item_code':  'have to be used to check the item code. Input is item_code',
            'search_item_by_keyword' : 'have to be used by assistant to find a match or a close match item based on the keyword provided by the user. Input is keyword',
            'create_address': 'have to be used by assistant to create address for customer.Input is JSON object serialized as a string.'
            #'check_sales_record': 'useful to check the sales invoice is exist. Input is name',
            #'get_item_price': 'have to be used by assistant to find the item price. Input is item_code',
        }
        return {
            'tools': tools,
        }


    # Cached company data to prevent unnecessary API calls
    company_cache = {}

    def get_cached_company(self, fields=None):
        self.connect()
        if not fields:
            fields = ['name']

        cache_key = str(fields)
        if cache_key not in self.company_cache:
            self.company_cache[cache_key] = self.client.get_documents('Company', fields=fields)

        return self.company_cache[cache_key]

    def _create_sales(self, doctype, data):
        """
          input is:
            {
              "due_date": "2023-05-31",
              "customer": "ksim",
              "items": [
                {
                  "name": "T-shirt--",
                  "description": "T-shirt",
                  "quantity": 1,
                  "rate": 20.3
                }
              ]
            }
        """
        if isinstance(data, string_types):
            data = json.loads(data)

        # Get company defaults
        self.handle_company_defaults(data)

        # Handle payment terms
        data['payment_terms_template'] = 'Full Payment Terms'
        print("Payment Terms")

        # Check dates
        if doctype == self.SALES_INVOICE:
            date = dt.datetime.strptime(data['due_date'], '%Y-%m-%d')
            if date < dt.datetime.today():
                return 'Error: due_date have to be in the future'
        elif doctype == self.SALES_ORDER:
            date = dt.datetime.strptime(data['delivery_date'], '%Y-%m-%d')
            if date < dt.datetime.today():
                return 'Error: delivery date have to be in the future'
        elif doctype == self.SALES_QUOTATION:
            date = dt.datetime.strptime(data['transaction_date'], '%Y-%m-%d')
            if date < dt.datetime.today():
                return 'Error: quotation date have to be in the future'
            data['party_name'] = data['customer']

        for item in data['items']:
            # Rename column
            if 'quantity' in item and 'qty' not in item:
                item['qty'] = item['quantity']
                del item['quantity']
            item_default = self.get_item_default({**item, 'company': data['company']})
            item['income_account'] = item_default['income_account']
            item['cost_center'] = item_default['selling_cost_center']
            item['warehouse'] = item_default['warehouse']
        print("Pass Dates")

        try:
            self.connect()
            response = self.client.post_document(doctype, data)
            success_msg = f"{doctype} : {response['name']} has been successfully created."
            print("generate pdf")
            pdf = self.generate_pdf_url(response)
            if pdf:
                success_msg += f" PDF URL:" + pdf
            return success_msg
        except Exception as e:
            print (e)
            return f"Error: {e}"

    def _update_sales(self, doctype, data):
        """
          input is:
            {
              "name": "ACC-SINV-2023-00070"
              "additional_discount_percentage": "10%" or "ten percent"
              "discount_amount": "$100" or "100 dollars"
            }
        """
        if isinstance(data, string_types):
            data = json.loads(data)
        # Get company defaults
        self.handle_company_defaults(data)

        #check that the due date is not prior to posting date
        if doctype == self.SALES_INVOICE:
            sales_details = self.get_sales_invoice_detail(data['name'])[0]
            if 'due_date' in data and data['due_date'].strip():
                due_date = dt.datetime.strptime(data['due_date'], '%Y-%m-%d')
                try:
                    posting_date_str = sales_details['posting_date']
                    posting_date = dt.datetime.strptime(posting_date_str, '%Y-%m-%d')
                    if due_date < posting_date:
                        return 'Error: due_date cannot be before invoice posting date'
                except ValueError as e:
                    return f'Error: {e}'
        elif doctype == self.SALES_ORDER:
             sales_details = self.get_sales_order_detail(data['name'])[0]
             if 'delivery_date' in data and data['delivery_date'].strip():
                delivery_date = dt.datetime.strptime(data['delivery_date'], '%Y-%m-%d')
                try:
                    transaction_date_str = sales_details['transaction_date']
                    transaction_date = dt.datetime.strptime(transaction_date_str, '%Y-%m-%d')
                    if delivery_date < transaction_date:
                        return 'Error: delivery_date cannot be before order transaction date'
                except ValueError as e:
                    return f'Error: {e}'
        elif doctype == self.SALES_QUOTATION:
             sales_details = self.get_sales_quotation_detail(data['name'])[0]
             if 'transaction_date' in data and data['transaction__date'].strip():
                transaction_date = dt.datetime.strptime(data['transaction_date'], '%Y-%m-%d')
                try:
                    transaction_date_str = sales_details['transaction_date']
                    transaction_date = dt.datetime.strptime(transaction_date_str, '%Y-%m-%d')
                    if transaction_date < dt.datetime.today():
                        return 'Error: transaction date cannot be in the past'
                except ValueError as e:
                    return f'Error: {e}'

        # Update discounts
        #if 'additional_discount_percentage' in data:
        #    data['additional_discount_percentage'] = "{:.3f}".format(float(data['additional_discount_percentage']))

        # Update items
        sales_items = sales_details['items']

        if 'items' in data and len(data['items']) > 0:
            existing_items_dict = {item['item_code']: item for item in sales_items}

            # 1. Removal of specified items
            to_remove = [item for item in data['items'] if item.get('remove', False)]
            for removal_item in to_remove:
                sales_items = [item for item in sales_items if item['item_code'] != removal_item['item_code']]

            # 2. Addition/Update of new or existing items
            for item in data['items']:
                if item.get('remove', False):  # Skip items marked for removal
                    continue

                item_details = self.search_item_by_keyword(item['item_code'])[0]
                item_default = self.get_item_default({**item, 'company': sales_details['company']})
                item['item_name'] = item_details['item_name']
                if 'description' not in item:
                    item['description'] = item_details.get('description','')
                item['uom'] = item_details['stock_uom']
                item['conversion_factor'] = 1
                item['income_account'] = item_default['income_account'] or sales_items[0]['income_account']
                item['cost_center'] = item_default['selling_cost_center'] or sales_items[0]['cost_center']
                item['rate'] = item.get('rate', 0)
                item['base_rate'] = item['rate']

                existing_item = existing_items_dict.get(item['item_code'], None)
                if existing_item:
                    # Update the existing item details
                    existing_index = sales_items.index(existing_item)
                    sales_items[existing_index] = item
                else:
                    sales_items.append(item)  # Append new item to sales_items

                if 'quantity' in item:
                    item['qty'] = item['quantity']
                elif 'qty' in item:
                    item['qty'] = item['qty']
                elif existing_item:
                    item['qty'] = existing_item['qty']
                if 'rate' not in item and existing_item and 'rate' in existing_item:
                    item['rate'] = existing_item['rate']
                item['amount'] = item['rate'] * item['qty']
                item['base_amount'] = item['amount']

                if not item['amount'] and item_default.get('rate'):
                    item['base_rate'] = item_details['rate'][0]['price_list_rate']
                    item['rate'] = item_details['rate'][0]['price_list_rate']
                    item['base_amount'] = item['rate'] * item['qty']
                    item['amount'] = item['rate'] * item['qty']

            for idx, item in enumerate(sales_items, start=1):
                item['idx'] = idx

        payload = {
            'doctype': doctype,
            'name': data['name'],
            'items': sales_items
        }

        if doctype == self.SALES_QUOTATION:
            if 'customer' in data and data['customer'].strip():
                    payload['party_name'] = data['customer']
                    payload['customer_name'] = data['customer']
                    payload['title'] = data['customer']
        else:
            if 'customer' in data and data['customer'].strip():
                    payload['customer'] = data['customer']
                    payload['title'] = data['title']

        if 'due_date' in data and data['due_date'].strip():
            payload['due_date'] = data['due_date']
        if 'additional_discount_percentage' in data:
            payload['additional_discount_percentage'] = data['additional_discount_percentage']
        if 'discount_amount' in data:
            payload['discount_amount'] = data['discount_amount']
        print("DATA:", data)
        print("PAYLOAD:", payload)

        try:
            self.connect()
            response = self.client.update_document(doctype, data['name'], payload)
            success_msg = f"{doctype} : {response['name']} has been successfully updated."
            pdf = self.generate_pdf_url(response)
            if pdf:
                success_msg += f" PDF URL:" + pdf
            return success_msg
        except Exception as e:
            return f"Error: {e}"

    def _submit_sales(self, doctype, data):
        """
            input is:
                {
                    "name": "ACC-SINV-2023-00070"
                }
        """
        if isinstance(data, string_types):
            data = json.loads(data)
        # Get company defaults
        self.handle_company_defaults(data)

        try:
            self.connect()
            # check the docstatus of the invoice
            sales_details = self.check_sales_record(doctype, data['name'], True)
            docstatus = sales_details['docstatus']

            # if the docstatus is 0 (Draft)
            if docstatus ==0:
                response = self.client.update_document(doctype, data['name'], data={"docstatus": 1})
                success_msg = f"{doctype} : {response['name']} has been successfully submitted."
                pdf = self.generate_pdf_url(response)
                if pdf:
                    success_msg += f" PDF URL:" + pdf
                return success_msg

            # if the docstatus is 1 (Unpaid/Overdue)
            elif docstatus == 1:
                return "Record already submitted"

            # if the docstatus is 2 (Cancelled)
            elif docstatus ==2:
                return "Record is cancelled"

            else:
                return f"Unexpected Doc Status: {docstatus}"
        except Exception as e:
            return f"Error: {e}"

    def _cancel_sales(self, doctype, data):
        """
            input is:
                {
                    "name": "ACC-SINV-2023-00070"
                }
        """
        if isinstance(data, string_types):
            data = json.loads(data)

        try:
            self.connect()
            # check the docstatus of the invoice
            sales_details = self.check_sales_record(doctype, data['name'], True)
            docstatus = sales_details['docstatus']

            # if the docstatus is 0 (Draft)
            if docstatus ==0:
                return "Unable to cancel record that is in Draft"

            # if the docstatus is 1 (Unpaid/Overdue)
            elif docstatus == 1:
                response = self.client.update_document(doctype, data['name'], data={"docstatus": 2})
                success_msg = f"{doctype} : {response['name']} has been successfully cancelled."
                pdf = self.generate_pdf_url(response)
                if pdf:
                    success_msg += f" PDF URL:" + pdf
                return success_msg

            # if the docstatus is 2 (Cancelled)
            elif docstatus ==2:
                return "Record already cancelled"

            else:
                return f"Unexpected Doc Status: {docstatus}"
        except Exception as e:
            return f"Error: {e}"

    def create_sales_quotation(self, data):
        return self._create_sales(doctype=self.SALES_QUOTATION, data=data)

    def create_sales_invoice(self, data):
        return self._create_sales(doctype=self.SALES_INVOICE, data=data)

    def create_sales_order(self, data):
        return self._create_sales(doctype=self.SALES_ORDER, data=data)

    def update_sales_quotation(self, data):
        return self._update_sales(doctype=self.SALES_QUOTATION, data=data)

    def update_sales_invoice(self, data):
        return self._update_sales(doctype=self.SALES_INVOICE, data=data)

    def update_sales_order(self, data):
        return self._update_sales(doctype=self.SALES_ORDER, data=data)

    def submit_sales_quotation(self, data):
        return self._submit_sales(doctype=self.SALES_QUOTATION, data=data)

    def submit_sales_invoice(self, data):
        return self._submit_sales(doctype=self.SALES_INVOICE, data=data)

    def submit_sales_order(self, data):
        return self._submit_sales(doctype=self.SALES_ORDER, data=data)

    def cancel_sales_quotation(self, data):
        return self._cancel_sales(doctype=self.SALES_QUOTATION, data=data)

    def cancel_sales_invoice(self, data):
        return self._cancel_sales(doctype=self.SALES_INVOICE, data=data)

    def cancel_sales_order(self, data):
        return self._cancel_sales(doctype=self.SALES_ORDER, data=data)

    def check_sales_record(self, doctype, name, return_full_data=False, for_pdf=False):
        result = self._get_sales_details(doctype, name, for_pdf)

        if result:
            return result[0] if return_full_data else True
        else:
            if return_full_data:
                raise ValueError(f"{doctype} {name} does not exist")
            else:
                return f"{doctype} {name} doesn't exist: please enter a valid invoice number"

    def _get_sales_details(self, doctype, name, for_pdf=False):
        if for_pdf:
            fields = ['name', 'company', 'letter_head', 'language']
        else:
            fields = ['name', 'company', 'currency', 'grand_total', 'status', 'docstatus', 'title']
            item_fields = ['name', 'idx', 'item_name', 'item_code', 'description', 'qty', 'rate', 'base_rate', 'uom', 'conversion_factor', 'amount', 'base_amount']
            if doctype == self.SALES_QUOTATION:
                fields.extend(['customer_name', 'transaction_date', 'valid_till'])
                #item_fields.extend(['income_account', 'cost_center'])
            elif doctype == self.SALES_INVOICE:
                fields.extend(['customer', 'posting_date', 'due_date', 'outstanding_amount'])
                item_fields.extend(['income_account', 'cost_center'])
            elif doctype == self.SALES_ORDER:
                fields.extend(['customer', 'transaction_date', 'delivery_date'])
                item_fields.extend(['delivery_date'])
        print("BREAK1")
        try:
            self.connect()
            data = self.client.get_documents(
                doctype, filters=[['name', '=', name]],
                fields=fields,
                limit=1)
            print("BREAK2")
            if for_pdf:
                return data[0]
            for i in data:
                i['items'] = self.client.get_documents(
                    f'{doctype} Item',
                    filters=[['parenttype', '=', doctype], ['parent', '=', i['name']]],
                    fields=item_fields,
                    parent=doctype
                )
            print("EVERYTHING:", data)
            return data
        except Exception as e:
            return f"Unable to get the details {doctype}: {name}. {e}"

    def get_sales_quotation_detail(self, name):
        return self._get_sales_details(self.SALES_QUOTATION, name)

    def get_sales_invoice_detail(self, name):
        return self._get_sales_details(self.SALES_INVOICE, name)

    def get_sales_order_detail(self, name):
        return self._get_sales_details(self.SALES_ORDER, name)

    def get_sales_quotation_pdf(self, name):
        data = self._get_sales_details(self.SALES_QUOTATION, name, True)
        data['doctype'] = self.SALES_QUOTATION
        return self.generate_pdf_url(data)

    def get_sales_invoice_pdf(self, name):
        data = self._get_sales_details(self.SALES_INVOICE, name, True)
        data['doctype'] = self.SALES_INVOICE
        return self.generate_pdf_url(data)

    def get_sales_order_pdf(self, name):
        data = self._get_sales_details(self.SALES_ORDER, name, True)
        data['doctype'] = self.SALES_ORDER
        return self.generate_pdf_url(data)

    def generate_pdf_url(self, data):
        # list all attributes
        base_url = "https://cloude8-v13beta-demo.cloude8.com"
        doctype = data.get('doctype')
        name = data.get('name')
        letter_head = data.get('letter_head')
        language = data.get('language')

        if not letter_head or letter_head == 'Blank Letterhead':
            company_letter_head = self.get_company_defaults(data['company'],['default_letter_head'])
            if company_letter_head:
                letter_head = company_letter_head['default_letter_head']

        pdf_url = (
            f"{base_url}/api/method/frappe.utils.print_format.download_pdf?"
            f"doctype={doctype}"
            f"&name={name}"
            f"&format=Standard"
            f"&no_letterhead=0"
            f"&letterhead={letter_head}"
            f"&settings=%7B%7D"
            f"&_lang={language}"
        )

        return pdf_url

    def register_payment_entry(self, data):
        """
          input is:
            {
              "posting_date": "2023-05-31",
              "payment_type": "Receive",
              "mode_of_payment": "Wire Transfer",
              "reference": [
                {
                  "reference_doctype": "Sales Invoice"
                  "reference_name": "ACC-SINV-2023-00097",
                }
              ]
            }
        """
        if isinstance(data, string_types):
            data = json.loads(data)

        date = dt.datetime.strptime(data['posting_date'], '%Y-%m-%d')
        if date < dt.datetime.today():
            return 'Error: posting date have to be in the future'

        for reference in data['reference_name']:
            # Reference type Sales Invoice
            data['reference_doctype'] = 'Sales Invoice'

        payment_number = None

        try:
            self.connect()
            response = self.client.post_document('Payment Entry', data)
            payment_number = response['name']
        except Exception as e:
            return f"Error: {e}"

        if payment_number is not None:
            return f"Payment Entry: {payment_number} has been successfully created"
        else:
            return f"Unable to create payment entry"


    def register_new_customer(self, data):
        """
        input is:
           {
             "customer_name": "John Doe",
             "customer_type": "Individual",
             "customer_group": "Individual",
             "territory": "All Territories",
           }
        """
        if isinstance(data, string_types):
            data = json.loads(data)

        try:
            self.connect()
            self.client.post_document('Customer', data)
        except Exception as e:
            return f"Error: {e}"
        return f"Success"

    def create_address(self, data):
        if isinstance(data, string_types):
            data = json.loads(data)

        required_keys = ['customer', 'address_line1', 'address_type', 'city', 'country']
        missing_keys = [key for key in required_keys if data.get(key) is None]
        if missing_keys:
            return f"Incomplete address information. Missing keys: {', '.join(missing_keys)}"

        payload = {
            'address_line1': data.get('address_line1'),
            'address_type': data.get('address_type'),
            'city': data.get('city'),
            'country': data.get('country'),
            'links': [{
                'link_doctype': 'Customer',
                'link_name': data.get('customer'),
                'link_title': data.get('customer')
            }]
        }

        try:
            self.connect()
            self.client.post_document('Address', payload)
        except Exception as e:
            return f"Unable to create address: {e}"
        return "Address has been successfully created"

    def check_item_code(self, item_code):
        self.connect()
        fields = ['name']
        result = self.client.get_documents('Item', filters=[['item_code', '=', item_code]],fields=fields)
        if len(result) == 1:
            return True
        return "Item doesn't exist: please search item by the keyword"

    def search_item_by_keyword(self, keyword):
        self.connect()
        fields = ['name', 'item_code', 'item_name', 'description', 'stock_uom', 'standard_rate', 'is_stock_item']
        result = []

        filters = [
            ['item_code', 'like', f'%{keyword}%'],
            ['name', 'like', f'%{keyword}%'],
            ['item_name', 'like', f'%{keyword}%']
        ]

        for filter_group in filters:
            result = self.client.get_documents('Item', filters=[filter_group], fields=fields)
            if result:
                break

        if result:
            for item in result:
                item['rate'] = self.get_item_price(item['item_code'])
            return result
        else:
            return "No items match the provided keyword. Please try a different keyword."

    def get_item_price(self, item_code):
        result = self.client.get_documents('Item Price', filters=[['item_code', '=', item_code],['selling', '=', 1]], fields=['name', 'valid_from', 'valid_upto', 'price_list_rate', 'currency', 'price_list'])
        if result:
            return result

    def get_item_default(self, item):
        self.connect()
        # Get company defaults
        company_defaults = self.get_company_defaults(item['company'], ['cost_center', 'default_income_account'])
        # Create the output dictionary with default values from the company
        output = {
            'buying_cost_center': company_defaults.get('cost_center', ''),
            'selling_cost_center': company_defaults.get('cost_center', ''),
            'income_account': company_defaults.get('default_income_account', ''),
            'warehouse': ''
        }
        # Get item defaults from the client
        result = self.client.get_documents('Item Default', filters=[['parenttype', '=', 'Item'], ['parent', '=', item['item_code']], ['company', '=', item['company']]], parent='Item')
        # Process the result if it exists
        if result:
            # Iterate through the results to find the first match
            for item_default in result:
                # Update output dictionary if a value is present in the result
                if item_default.get('selling_cost_center') and item_default['selling_cost_center'] != output['selling_cost_center']:
                    output['selling_cost_center'] = item_default['selling_cost_center']
                if item_default.get('buying_cost_center') and item_default['buying_cost_center'] != output['buying_cost_center']:
                    output['buying_cost_center'] = item_default['buying_cost_center']
                if item_default.get('income_account') and item_default['income_account'] != output['income_account']:
                    output['income_account'] = item_default['income_account']
                output['warehouse'] = item_default['default_warehouse']
                break  # Break out of the loop after updating the output once

        return output

    def get_company_defaults(self, company, fields=["*"]):
        result = self.client.get_documents('Company', filters=[['name', '=', company]], fields=fields)
        return result[0] if result else None

    def get_company(self, fields=None):
        self.connect()
        if fields == 'None':
            fields = ['name']
        result = self.client.get_documents('Company', fields=fields)
        return result[0] if result else None

    def handle_company_defaults(self, data):
        if not data.get('company'):
            data['company'] = self.get_cached_company()[0]['name']
        if not data.get('letter_head'):
            company_letter_head = self.get_company_defaults(data['company'], ['default_letter_head'])
            if company_letter_head:
                data['letter_head'] = company_letter_head['default_letter_head']

        terms_and_conditions = self.get_terms_and_conditions_defaults(data['company'])
        if terms_and_conditions:
            data.setdefault('tc_name', terms_and_conditions['name'])
            data.setdefault('terms', terms_and_conditions['terms'])

    def check_company_exists(self, name):
        self.connect()
        result = self.client.get_documents('Company', filters=[['name', '=', name]])
        if len(result) == 1:
            return True
        return "Company doesn't exist: please use a different name"

    def get_terms_and_conditions_defaults(self, company, fields=["*"]):
        result = self.client.get_documents('Terms and Conditions', filters=[['company', '=', company]], fields=fields)
        return result[0] if result else None

    def check_customer_exists(self, name):
        self.connect()

        result = self.client.get_documents('Customer', filters=[['name', '=', name]])
        if len(result) == 1:
            return True
        return "Customer doesn't exist"

        # Attempt to get cached company data
        #company_info = self.get_cached_company(fields=['name'])

        # If cache doesn't exist or is empty, fetch from the API
        #if not company_info:
        #    company_info = self.get_company(fields=['name'])
        #    self.company_cache = company_info

        # Extract company name from the retrieved data
        #company_name = company_info[0]['name'] if company_info else None
        #print("COmpany:", company_name)

        #if company_name:
        #    result = self.client.get_documents('Customer', filters=[['name', '=', name], ['company', '=', company_name]])
        #else:
        #    result = self.client.get_documents('Customer', filters=[['name', '=', name]])

        #if len(result) == 1:
        #    return True
        #return "Customer doesn't exist"

    def search_customer_by_name(self, name):
        self.connect()
        fields = ['name', 'customer_name']
        result = []

        filters = [
            ['name', 'like', f'%{name}%'],
            ['customer_name', 'like', f'%{name}%']
        ]

        for filter_group in filters:
            result = self.client.get_documents('Customer', filters=[filter_group], fields=fields)
            if result:
                break

        if result:
            return result
        else:
            return "No customer found with the given name."

    def connect(self) -> FrappeClient:
        """Creates a new  API client if needed and sets it as the client to use for requests.

        Returns newly created Frappe API client, or current client if already set.
        """
        if self.is_connected is True and self.client:
            return self.client

        if self.domain and self.access_token:
            self.client = FrappeClient(self.domain, self.access_token)

        self.is_connected = True
        return self.client

    def check_connection(self) -> StatusResponse:
        """Checks connection to Frappe API by sending a ping request.

        Returns StatusResponse indicating whether or not the handler is connected.
        """

        response = StatusResponse(False)

        try:
            client = self.connect()
            client.ping()
            response.success = True

        except Exception as e:
            logger.error(f'Error connecting to Frappe API: {e}!')
            response.error_message = e

        self.is_connected = response.success
        return response

    def native_query(self, query: str = None) -> Response:
        ast = parse_sql(query, dialect='mindsdb')
        return self.query(ast)

    def _document_to_dataframe_row(self, doctype, document: Dict) -> Dict:
        return {
            'doctype': doctype,
            'data': json.dumps(document)
        }

    def _get_document(self, params: Dict = None) -> pd.DataFrame:
        client = self.connect()
        doctype = params['doctype']
        document = client.get_document(doctype, params['name'])
        return pd.DataFrame.from_records([self._document_to_dataframe_row(doctype, document)])

    def _get_documents(self, params: Dict = None) -> pd.DataFrame:
        client = self.connect()
        doctype = params['doctype']
        limit = params.get('limit', None)
        filters = params.get('filters', None)
        fields = params.get('fields', None)
        parent = params.get('parent', None)
        documents = client.get_documents(doctype, limit=limit, fields=fields, filters=filters, parent=parent)
        return pd.DataFrame.from_records([self._document_to_dataframe_row(doctype, d) for d in documents])

    def _create_document(self, params: Dict = None) -> pd.DataFrame:
        client = self.connect()
        doctype = params['doctype']
        # return new sales invoice number as well
        new_document = client.post_document(doctype, json.loads(params['data']))
        return pd.DataFrame.from_records([self._document_to_dataframe_row(doctype, new_document)]), new_document['name']
        #new_document = client.post_document(doctype, json.loads(params['data']))
        #return pd.DataFrame.from_records([self._document_to_dataframe_row(doctype, new_document)])

    def _update_document(self, params: Dict = None) -> pd.DataFrame:
        client = self.connect()
        doctype = params['doctype']
        edit_document = client.put_document(doctype, params['name'], json.loads(params['data']))
        return pd.DataFrame.from_records([self._document_to_dataframe_row(doctype, edit_document)])

    def call_frappe_api(self, method_name: str = None, params: Dict = None) -> pd.DataFrame:
        """Calls the Frappe API method with the given params.

        Returns results as a pandas DataFrame.

        Args:
            method_name (str): Method name to call (e.g. get_document)
            params (Dict): Params to pass to the API call
        """
        if method_name == 'get_documents':
            return self._get_documents(params)
        if method_name == 'get_document':
            return self._get_document(params)
        if method_name == 'create_document':
            return self._create_document(params)
        if method_name == 'update_document':
            return self._update_document (params)
        raise NotImplementedError('Method name {} not supported by Frappe API Handler'.format(method_name))

    def get_agent_tools(self, key, token_path):
        """
        Returns a list of tools that can be used by an agent
        """
        fernet = Fernet(key)

        with open(token_path, 'rb') as f:
            encrypted_token = f.read()
        decrypted_token = fernet.decrypt(encrypted_token).decode()
        domain, access_token = decrypted_token.strip().split("\n")
        self.access_token = access_token
        self.domain = domain

        tool_dict = self.back_office_config()['tools']
        all_tools = []
        for tool in tool_dict:
            all_tools.append(Tool.from_function(
                func=getattr(self, tool),
                name=tool,
                description=tool_dict[tool]
            ))
        return all_tools
