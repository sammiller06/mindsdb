import json
import pandas as pd
import datetime as dt
import difflib
from typing import Dict

from mindsdb.integrations.handlers.frappe_handler.frappe_tables import FrappeDocumentsTable
from mindsdb.integrations.handlers.frappe_handler.frappe_client import FrappeClient
from mindsdb.integrations.libs.api_handler import APIHandler
from mindsdb.integrations.libs.response import (
    HandlerStatusResponse as StatusResponse,
    HandlerResponse as Response,
)
from mindsdb.utilities import log
from mindsdb_sql import parse_sql

class FrappeHandler(APIHandler):
    """A class for handling connections and interactions with the Frappe API.

    Attributes:
        client (FrappeClient): The `FrappeClient` object for interacting with the Frappe API.
        is_connected (bool): Whether or not the API client is connected to Frappe.
        domain (str): Frappe domain to send API requests to.
        access_token (str): OAuth token to use for authentication.
    """

    def __init__(self, name: str = None, **kwargs):
        """Registers all API tables and prepares the handler for an API connection.

        Args:
            name: (str): The handler name to use
        """
        super().__init__(name)
        self.client = None
        self.is_connected = False

        args = kwargs.get('connection_data', {})
        if not 'access_token' in args:
            raise ValueError('"access_token" parameter required for authentication')
        if not 'domain' in args:
            raise ValueError('"domain" parameter required to connect to your Frappe instance')
        self.access_token = args['access_token']
        self.domain = args['domain']

        document_data = FrappeDocumentsTable(self)
        self._register_table('documents', document_data)
        self.connection_data = args

    def back_office_config(self):
        tools = {
            'register_sales_invoice': 'have to be used by assistant to register a sales invoice. Input is JSON object serialized as a string. Due date have to be passed in format: "yyyy-mm-dd".',
            'register_new_customer': 'have to be used by assistant to register a new customer. Input is JSON object serliazed as a string',
            'submit_sales_invoice': 'have to be used by assistant to submit a sales invoice. Input is JSON object serialized as a string',
            'update_sales_invoice': 'have to be used by assistant to update a sales invoice. Input is JSON object serialized as a string',
            'cancel_sales_invoice': 'have to be used by assistant to cancel a sales invoice. Input is JSON object serialized as a string',
            'register_payment_entry': 'have to be used by assistant to create a payment entry. Input is JSON object serialized as a string',
            'check_company_exists': 'useful to check the company is exist using fuzzy search. Input is company',
            'check_sales_invoice': 'useful to check the sales invoice is exist. Input is name',
            'check_customer':  'useful to search for existing customers. Input is customer',
            'check_item_code':  'have to be used to check the item code. Input is item_code',
            'search_item_by_keyword' : 'have to be used by assistant to find a match or a close match item based on the keyword provided by the user',
        }
        return {
            'tools': tools,
        }

    def register_sales_invoice(self, data):
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
        invoice = json.loads(data)
        if not invoice.get('company'):
            invoice['company'] = self.get_permitted_company()[0]['name']
        date = dt.datetime.strptime(invoice['due_date'], '%Y-%m-%d')
        if date < dt.datetime.today():
            return 'Error: due_date have to be in the future'

        for item in invoice['items']:
            # rename column
            item['qty'] = item['quantity']
            del item['quantity']
            if not item.get('company'):
                item['company'] = invoice['company']
            item_default = self.get_item_default(item)
            item['income_account'] = item_default['income_account']
            item['cost_center'] = item_default['selling_cost_center']

        #invoice['tc_name'] = "TNP Terms and Conditions"

        invoice_number = None

        try:
            self.connect()
            #self.client.post_document('Sales Invoice', invoice)
            response_data, invoice_number = self.client.post_document('Sales Invoice', invoice)
        except Exception as e:
            return f"Error: {e}"

        if invoice_number is not None:
            return f"Invoice Number: {invoice_number} has been successfully created"
        else:
            return f"Unable to create invoice"

    def update_sales_invoice(self, data):
        """
          input is:
            {
              "name": "ACC-SINV-2023-00070"
            }
        """
        invoice = json.loads(data)

        #check that the due date is not prior to posting date
        if 'due_date' in invoice and invoice['due_date'].strip():
           due_date = dt.datetime.strptime(invoice['due_date'], '%Y-%m-%d')
           try:

               invoice_data = self.check_sales_invoice(invoice['name'], True)
               posting_date_str = invoice_data['posting_date']
               posting_date = dt.datetime.strptime(posting_date_str, '%Y-%m-%d')
               if due_date < posting_date:
                   return 'Error: due_date cannot be before invoice posting date'
           except ValueError as e:
               return f'Error: {e}'

        #update title with customer name
        if 'customer' in invoice and invoice['customer'].strip():
             invoice['title'] = invoice['customer']

        # adding new items
        if 'items' in invoice and len(invoice['items']) > 0:
            # fetch existing items from the invoice data
            existing_items = []
            invoice_data = self.check_sales_invoice_item(invoice['name'], True)
            if 'items' in invoice_data and len(invoice_data['items']) > 0:
                existing_items = invoice_data['items']

            for item in invoice['items']:
                # rename column
                item['qty'] = item['quantity']
                del item['quantity']

            # merge existing and new items
            invoice_data['items'] = existing_items + invoice['items']

        # if no new items, copy over the existing items
        elif 'items' in invoice_data and len(invoice_data['items']) > 0:
            invoice['items'] = invoice_data['items']

        try:
            self.connect()
            self.client.update_document('Sales Invoice', invoice['name'], invoice)
        except Exception as e:
            return f"Error: {e}"
        return f"Success"

    def submit_sales_invoice(self, data):
        """
        input is:
           {
              "name": "ACC-SINV-2023-00070"
           }
        """

        invoice = json.loads(data)

        try:
            self.connect()
            # check the docstatus of the invoice
            invoice_data = self.check_sales_invoice(invoice['name'], True)
            docstatus = invoice_data['docstatus']

            # if the docstatus is 0 (Draft)
            if docstatus ==0:
                self.client.update_document('Sales Invoice', invoice['name'], data={"docstatus": 1})
                return f"Success"

            # if the docstatus is 1 (Unpaid)
            elif docstatus == 1:
                return "Invoice already submitted"

            # if the docstatus is 2 (Cancelled)
            elif docstatus ==2:
                return "Invoice is cancelled"

            else:
                return f"Unexpected Doc Status: {docstatus}"
        except Exception as e:
            return f"Error: {e}"

    def cancel_sales_invoice(self, data):
        """
        input is:
           {
              "name": "ACC-SINV-2023-00070"
           }
        """

        invoice = json.loads(data)

        try:
            self.connect()
            # check the docstatus of the invoice
            invoice_data = self.check_sales_invoice(invoice['name'], True)
            docstatus = invoice_data['docstatus']

            # if the docstatus is 0 (Draft)
            if docstatus ==0:
                return "Unable to cancel invoice that is in Draft"

            # if the docstatus is 1 (Unpaid)
            elif docstatus == 1:
                self.client.update_document('Sales Invoice', invoice['name'], data={"docstatus": 2})
                return f"Success"

            # if the docstatus is 2 (Cancelled)
            elif docstatus ==2:
                return "Invoice already cancelled"

            else:
                return f"Unexpected Doc Status: {docstatus}"
        except Exception as e:
            return f"Error: {e}"

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
        payment_entry = json.loads(data)
        date = dt.datetime.strptime(payment_entry['posting_date'], '%Y-%m-%d')
        if date < dt.datetime.today():
            return 'Error: posting date have to be in the future'

        for reference in payment_entry['reference_name']:
            # Reference type Sales Invoice
            payment_entry['reference_doctype'] = 'Sales Invoice'

        payment_number = None

        try:
            self.connect()
            response_data, payment_number = self.client.post_document('Payment Entry', payment_entry)
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
             "name": "John Doe"
           }
        """

        customer_name = json.loads(data)

        try:
            self.connect()
            self.client.post_document('Customer', customer_name)
        except Exception as e:
            return f"Error: {e}"
        return f"Success"

    def check_item_code(self, item_code):
        self.connect()
        result = self.client.get_documents('Item', filters=[['item_code', '=', item_code]])
        if len(result) == 1:
            return True
        return "Item doesn't exist: please use different name"
   
    def search_item_by_keyword(self, keyword):
        self.connect()
        result = self.client.get_documents('Item', filters=[['name', 'like', f'%{keyword}%']], fields=['name', 'item_code', 'description', 'company'])
        if len(result):
            for item in result:
                item['rate'] = self.get_item_price(item['item_code'])
            return result
        return "No item match with the provided key, please use a different keyword"

    def get_item_price(self, item_code):
        result = self.client.get_documents('Item Price', filters=[['item_code', '=', item_code],['selling', '=', 1]], fields=['name', 'valid_from', 'valid_upto', 'price_list_rate', 'currency', 'price_list'])
        if result:
            return result
    
    def get_item_default(self, item):
        # Get company defaults
        company_defaults = self.get_company_defaults(item['company'], ["cost_center", "default_income_account"])
        # Create the output dictionary with default values from the company
        output = {
            'buying_cost_center': company_defaults.get('cost_center', ''),
            'selling_cost_center': company_defaults.get('cost_center', ''),
            'income_account': company_defaults.get('default_income_account', '')
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
                break  # Break out of the loop after updating the output once

        return output

    def get_company_defaults(self, company, fields=["*"]):
        result = self.client.get_documents('Company', filters=[['name', '=', company]], fields=fields)
        return result[0]
    
    def get_permitted_company(self):
        result = self.client.get_documents('Company', fields=['name'])
        return result
    
    def check_company_exists(self, name):
        self.connect()
        result = self.client.get_documents('Company', filters=[['name', '=', name]])
        if len(result) == 1:
            return True
        return "Company doesn't exist: please use different name"

    def check_sales_invoice(self, name, return_full_data=False):
        self.connect()
        result = self.client.get_documents('Sales Invoice', filters=[['name', '=', name]])
        if len(result) == 1:
            return result[0] if return_full_data else True
        else:
            if return_full_data:
               raise ValueError(f"Sales Invoice {name} does not exist")
            else:
               return "Sales Invoice doesn't exist: please enter a valid invoice number"

    def check_sales_invoice_item(self, name, return_full_data=False):
        self.connect()
        result = self.client.get_documents('Sales Invoice Item', 'parent', ':', name)
        if len(result) == 1:
            return result[0] if return_full_data else True
        else:
            if return_full_data:
               raise ValueError(f"Sales Invoice {parent} does not exist")
            else:
               return "Sales Invoice doesn't exist: please enter a valid invoice number"

    def check_customer(self, name):
        self.connect()

        #for fuzzy search logic
        #result = self.client.get_documents('Customer', filters=[['name', 'like', "%" + name + "%"]])
        #if len(result) == 0:
        #    return "Customer doesn't exist"
        #elif len(result) == 1 and result[0]['name'].lower() == name.lower():
        #    return True
        #else:
            #If there are multiple customers with similar names, list them and ask user to confirm
        #    similar_names = [doc['name'] for doc in result if difflib.SequenceMatcher(None, doc['name'].lower(), name.lower()).ratio() > 0.6]
        #    if len(similar_names) > 0:
        #        return f"There are multiple customers with that name, which did you mean? ({', '.join(similar_names)})"
        #    else:
        #        return "Customer doesn't exist"

        #exact name search
        result = self.client.get_documents('Customer', filters=[['name', '=', name]])
        if len(result) == 1:
            return True
        return "Customer doesn't exist"

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
            log.logger.error(f'Error connecting to Frappe API: {e}!')
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
        documents = client.get_documents(doctype, limit=limit, fields=fields, filters=filters)
        return pd.DataFrame.from_records([self._document_to_dataframe_row(doctype, d) for d in documents])

    def _create_document(self, params: Dict = None) -> pd.DataFrame:
        client = self.connect()
        doctype = params['doctype']
        # return new sales invoice number as well
        new_document, invoice_number = client.post_document(doctype, json.loads(params['data']))
        return pd.DataFrame.from_records([self._document_to_dataframe_row(doctype, new_document)]), invoice_number
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
