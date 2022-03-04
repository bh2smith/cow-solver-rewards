# Code mostly copied from: https://github.com/itzmestar/duneanalytics

"""This provides the DuneAnalytics class implementation"""
from __future__ import annotations

import os
import time
from datetime import datetime
from enum import Enum
from typing import Optional, Any

from requests import Session

from src.models import Network

# --------- Constants --------- #
BASE_URL = "https://dune.xyz"
GRAPH_URL = 'https://core-hsr.duneanalytics.com/v1/graphql'


# --------- Constants --------- #

class DuneParameterType(Enum):
    """
    Enum of the 4 distinct dune parameter types
    """
    TEXT = 'text'
    NUMBER = 'number'
    DATE = 'datetime'
    LIST = 'list'


class QueryParameter:
    """Class whose instances are Dune Compatible Query Parameters"""

    def __init__(
            self,
            name: str,
            parameter_type: DuneParameterType,
            raw_value: Any,
            value_str: str
    ):
        self.key: str = name
        self.type: DuneParameterType = parameter_type
        self.value_str = value_str
        self.original_value = raw_value

    @classmethod
    def text_type(cls, name: str, value: str):
        """Constructs a Query parameter of type text"""
        return cls(
            name,
            DuneParameterType.TEXT,
            raw_value=value,
            value_str=value,
        )

    @classmethod
    def number_type(cls, name: str, value: int | float):
        """Constructs a Query parameter of type number"""
        return cls(
            name,
            DuneParameterType.NUMBER,
            raw_value=value,
            value_str=str(value),
        )

    @classmethod
    def date_type(cls, name: str, value: datetime):
        """Constructs a Query parameter of type date"""
        return cls(
            name,
            DuneParameterType.DATE,
            raw_value=value,
            # This is the postgres string format of timestamptz
            value_str=value.strftime("%Y-%m-%d %H:%M:%S"),
        )

    @classmethod
    def list_type(cls, name: str, value: list[str]):
        """Constructs a Query parameter of type list"""
        return cls(
            name,
            DuneParameterType.LIST,
            raw_value=value,
            value_str="\n".join(value),
        )

    def to_dict(self) -> dict[str, str]:
        """Converts QueryParameter into string json format accepted by Dune API"""
        return {
            "key": self.key,
            "type": self.type.value,
            "value": self.value_str,
        }

    def value(self) -> Any:
        """Returns the parameter value in the original type provided"""
        return self.original_value


class DuneAnalytics:
    """
    DuneAnalytics class to act as python client for duneanalytics.com.
    All requests to be made through this class.
    """

    def __init__(
            self,
            username: str,
            password: str,
            query_id: int
    ):
        """
        Initialize the object
        :param username: username for duneanalytics.com
        :param password: password for duneanalytics.com
        :param query_id: existing integer query id owned `username`
        """
        self.csrf = None
        self.auth_refresh = None
        self.token = None
        self.username = username
        self.password = password
        self.query_id = int(query_id)
        self.session = Session()
        headers = {
            'origin': BASE_URL,
            'sec-ch-ua-mobile': '?0',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'dnt': '1',
        }
        self.session.headers.update(headers)

    @staticmethod
    def new_from_environment():
        """
        Initialize and authenticate a Dune client from the current environment.
        """
        dune = DuneAnalytics(
            os.environ['DUNE_USER'],
            os.environ['DUNE_PASSWORD'],
            int(os.environ['DUNE_QUERY_ID']),
        )
        dune.login()
        dune.fetch_auth_token()
        return dune

    def login(self):
        """
        Try to log in to duneanalytics.com & get the token
        """
        login_url = BASE_URL + '/auth/login'
        csrf_url = BASE_URL + '/api/auth/csrf'
        auth_url = BASE_URL + '/api/auth'

        # fetch login page
        self.session.get(login_url)

        # get csrf token
        self.session.post(csrf_url)
        self.csrf = self.session.cookies.get('csrf')

        # try to log in
        form_data = {
            'action': 'login',
            'username': self.username,
            'password': self.password,
            'csrf': self.csrf,
            'next': BASE_URL
        }

        self.session.post(auth_url, data=form_data)
        self.auth_refresh = self.session.cookies.get('auth-refresh')

    def fetch_auth_token(self):
        """
        Fetch authorization token for the user
        """
        session_url = BASE_URL + '/api/auth/session'

        response = self.session.post(session_url)
        if response.status_code == 200:
            self.token = response.json().get('token')
        else:
            print(response.text)

    def login_and_fetch_auth(self):
        """combines both of `login` and `fetch_auth_token`"""
        # It seems login does both anyway.
        self.login()
        self.fetch_auth_token()

    def initiate_new_query(
            self,
            query: str,
            query_name: str,
            network: Network,
            parameters: list[QueryParameter]
    ):
        """
        Initiates a new query
        """
        dune_network_map = {
            Network.MAINNET: 4,
            Network.GCHAIN: 6
        }
        query_data = {
            "operationName": "UpsertQuery",
            "variables": {
                "favs_last_24h": False,
                "favs_last_7d": False,
                "favs_last_30d": False,
                "favs_all_time": True,
                "object": {
                    "id": self.query_id,
                    "schedule": None,
                    "dataset_id": dune_network_map[network],
                    "name": query_name,
                    "query": query,
                    "user_id": 84,
                    "description": "",
                    "is_archived": False,
                    "is_temp": False,
                    "tags": [],
                    "parameters": [p.to_dict() for p in parameters],
                    "visualizations": {
                        "data": [],
                        "on_conflict": {
                            "constraint": "visualizations_pkey",
                            "update_columns": ["name", "options"]
                        }
                    }
                },
                "on_conflict": {
                    "constraint": "queries_pkey",
                    "update_columns": ["dataset_id", "name", "description", "query",
                                       "schedule",
                                       "is_archived", "is_temp", "tags", "parameters"]
                },
                "session_id": 84
            },
            # pylint: disable=line-too-long
            "query": "mutation UpsertQuery($session_id: Int!, $object: queries_insert_input!, $on_conflict: queries_on_conflict!, $favs_last_24h: Boolean! = false, $favs_last_7d: Boolean! = false, $favs_last_30d: Boolean! = false, $favs_all_time: Boolean! = true) {\n  insert_queries_one(object: $object, on_conflict: $on_conflict) {\n    ...Query\n    favorite_queries(where: {user_id: {_eq: $session_id}}, limit: 1) {\n      created_at\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment Query on queries {\n  ...BaseQuery\n  ...QueryVisualizations\n  ...QueryForked\n  ...QueryUsers\n  ...QueryFavorites\n  __typename\n}\n\nfragment BaseQuery on queries {\n  id\n  dataset_id\n  name\n  description\n  query\n  private_to_group_id\n  is_temp\n  is_archived\n  created_at\n  updated_at\n  schedule\n  tags\n  parameters\n  __typename\n}\n\nfragment QueryVisualizations on queries {\n  visualizations {\n    id\n    type\n    name\n    options\n    created_at\n    __typename\n  }\n  __typename\n}\n\nfragment QueryForked on queries {\n  forked_query {\n    id\n    name\n    user {\n      name\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment QueryUsers on queries {\n  user {\n    ...User\n    __typename\n  }\n  __typename\n}\n\nfragment User on users {\n  id\n  name\n  profile_image_url\n  __typename\n}\n\nfragment QueryFavorites on queries {\n  query_favorite_count_all @include(if: $favs_all_time) {\n    favorite_count\n    __typename\n  }\n  query_favorite_count_last_24h @include(if: $favs_last_24h) {\n    favorite_count\n    __typename\n  }\n  query_favorite_count_last_7d @include(if: $favs_last_7d) {\n    favorite_count\n    __typename\n  }\n  query_favorite_count_last_30d @include(if: $favs_last_30d) {\n    favorite_count\n    __typename\n  }\n  __typename\n}\n",
        }
        self.handle_dune_request(query_data)

    def execute_query(self):
        """
        Executes query according to the given id.
        """
        query_data = {
            "operationName": "ExecuteQuery",
            "variables": {
                "query_id": self.query_id,
                "parameters": []
            },
            "query":
                "mutation ExecuteQuery($query_id: Int!, $parameters: [Parameter!]!)"
                "{\n  execute_query(query_id: $query_id, parameters: $parameters) "
                "{\n    job_id\n    __typename\n  }\n}\n"}
        self.handle_dune_request(query_data)

    def query_result_id(self):
        """
        Fetch the query result id for a query
        :return: result_id
        """
        query_data = {
            "operationName": "GetResult",
            "variables": {"query_id": self.query_id},
            "query": "query GetResult($query_id: Int!, $parameters: [Parameter!]) "
                     "{\n  get_result(query_id: $query_id, parameters: $parameters) "
                     "{\n    job_id\n    result_id\n    __typename\n  }\n}\n"
        }

        data = self.handle_dune_request(query_data)
        result_id = data.get('data').get('get_result').get('result_id')
        return result_id

    def query_result(self, result_id):
        """
        Fetch the result for a query
        :param result_id: result id of the query
        """
        query_data = {
            "operationName": "FindResultDataByResult",
            "variables": {"result_id": result_id},
            "query": "query FindResultDataByResult($result_id: uuid!) "
                     "{\n  query_results(where: {id: {_eq: $result_id}}) "
                     "{\n    id\n    job_id\n    error\n    runtime\n    "
                     "generated_at\n    columns\n    __typename\n  }"
                     "\n  get_result_by_result_id(args: {want_result_id: $result_id}) "
                     "{\n    data\n    __typename\n  }\n}\n"
        }

        return self.handle_dune_request(query_data)

    def handle_dune_request(self, query):
        """
        Parses response for errors by key and raises runtime error if they exist.
        Successful responses will be printed to std-out and response json returned
        :param query: JSON content for request POST
        :return: response in json format
        """
        self.session.headers.update({'authorization': f'Bearer {self.token}'})
        response = self.session.post(GRAPH_URL, json=query)
        response_json = response.json()
        if 'errors' in response_json:
            raise RuntimeError("Dune API Request failed with", response_json)
        return response_json

    # pylint: disable=too-many-arguments
    def query_initiate_execute_await(
            self,
            query_filepath: str,
            network: Network,
            parameters: Optional[list[QueryParameter]] = None,
            max_retries: int = 2,
            ping_frequency: int = 5
    ) -> list[dict]:
        """
        Pushes new query to dune and executes, awaiting query completion
        """
        self.initiate_new_query(
            query=self.open_query(query_filepath),
            network=network,
            query_name="Auto Generated Query",
            parameters=parameters or []
        )
        for _ in range(0, max_retries):
            try:
                return self.execute_and_await_results(ping_frequency)
            except RuntimeError as err:
                print(
                    f"execution fetching failed with {err}.\n"
                    f"re-establishing dune connection and trying again"
                )
                self.login_and_fetch_auth()
        raise Exception(f"Maximum retries ({max_retries}) exceeded")

    def execute_and_await_results(self, sleep_time) -> list[dict]:
        """
        Executes query by ID and awaits completion.
        Since queries take some time to complete we include a sleep parameter
        since there is no purpose in constantly pinging for results
        :param sleep_time: time to sleep between checking for results
        :return: parsed list of dict records returned from query
        """
        self.execute_query()
        result_id = self.query_result_id()
        while not result_id:
            time.sleep(sleep_time)
            result_id = self.query_result_id()
        data = self.query_result(result_id)
        data_set = parse_dune_response(data)
        print(f"got {len(data_set)} records from last query")
        return data_set

    @classmethod
    def open_query(cls, filepath: str) -> str:
        """Opens `filename` and returns as string"""
        with open(filepath, 'r', encoding='utf-8') as query_file:
            return query_file.read()

    def fetch(
            self,
            query_filepath: str,
            network: Network,
            name: str,
            parameters: Optional[list[QueryParameter]],
    ) -> list[dict]:
        """
        :param query_filepath: path to sql file to execute
        :param network: 'mainnet' or 'gchain'
        :param name: optional name of what is being fetched (for logging)
        :param parameters: optional parameters to be included in query
        :return: list of records as dictionaries
        """
        print(f"Fetching {name} on {network}...")
        return self.query_initiate_execute_await(
            query_filepath,
            network,
            parameters
        )


def parse_dune_response(data: dict) -> list[dict]:
    """Parses user data and execution date from query result."""
    return [rec['data'] for rec in data["data"]["get_result_by_result_id"]]
