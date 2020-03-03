#!/usr/bin/env python

#Imports
import boto3
import collections
import datetime
import json
import os
import random
import re
import redis
import string
import threading
import time

#Client Error
from botocore.exceptions import (ClientError, NoCredentialsError, ProfileNotFound)
from redis.exceptions import (ResponseError, TimeoutError)

#Meta
__author__ = "ahitchin"
__version__ = '1.0.0'
__version_info__ = tuple(__version__.split("."))
__all__ = ["RedisWrapper"]

#Global
_DEFAULT_REGION = "us-east-1"

class RedisWrapper():
    def __init__(self, aws_name=None, hostname=None, port=6379, database=0, auth_token=None, ssl=True, **kwargs):
        """Init for class.
        
        :param aws_name: String cache name in AWS
        :param hostname: String hostname for cache
        :param port: Integer port to connect to cache with
        :param database: Integer database ID to connect to
        :param auth_token: String with password to cache
        :param ssl: Boolean to dictate if connection is with SSL or not
        :param kwargs.aws_profile: AWS Profile to grab from ~/.aws/credentials
        :param kwargs.aws_access_key_id: AWS Access Key ID
        :param kwargs.aws_secret_access_key: AWS Secret Access Key
        :param kwargs.aws_session_token: AWS Session Token
        :param kwargs.aws_region: AWS Region
        :return values: Dictionary with keys and their value type, and value 
        """
        #Fail if Hostname and Aws Name are Undefined
        if not any([aws_name, hostname]):
            raise Exception("'aws_name' or 'hostname' must be defined")

        #Null Vars
        self.aws_facts = None
        self.aws_parameters = None
        self.database_num = None
            
        #Init Vars
        self.aws_name = aws_name
        self.auth_token = auth_token
        self.database = database
        self.ssl = ssl

        #Get AWS Client
        self.aws_client = self._boto3_client(**kwargs)

        #Get Connection Vars
        self.hostname, self.port = self._cache_connection_variables(hostname, port)
        
        #Get Redis Client
        self.redis_conn = self._redis_client()

        #Get Cache Parameters in Background if Credentials are Given
        param_thread = threading.Thread(target=self._cache_parameters, args=())
        param_thread.start()
   
    def change_database_connection(self, db):
        """Change database connection to specified number.

        :param db: Integer specifying database id to switch connection to
        :return db_changed: Array of dictionarys with client information
        """
        #Template Command
        command = "SELECT {0}".format(db)

        #Change Database on Object Connection
        response = self.server_command(command)

        #Boolean to Track Operation Results
        db_changed = (response.lower() == "ok")

        #Update on Object
        self.database = db

        return db_changed

    def client_connected(self):
        """Get current clients connected to server.

        :return encoded: Array of dictionarys with client information
        """
        #Get Clients List
        response = self.redis_conn.client_list()

        #Convert data to utf-8
        encoded = RedisWrapper._convert(response)

        return encoded
    
    def client_connected_num(self):
        """Get number of current clients connected to server.

        :return connections: Integer of how many connected clients there are
        """
        #Get Client List
        response = self.redis_conn.client_list()

        #Get Length of Return Array
        connections = len(response)

        return connections

    def client_kill(self, address):
        """Kills a specific client when given an address.

        :param address: String specifying which key to get
        :return response: Boolean showing result of client kill call
        """
        #Kill Connected Client
        try:
            response = self.redis_conn.client_kill(address)
        except ResponseError as e:
            if e.message.lower() == "no such client":
                response = False
            else:
                raise e

        return response
    
    def client_kill_all(self):
        """Kills all clients connected except connection from self.

        :param address: String specifying which key to get
        :return response: Boolean showing result of client kill call
        """
        #Track Client Kills
        client_track = []

        #Get All Clients
        clients = self.client_connected()

        #Iter Clients and Kill
        for client in clients:
            #Get Client Address
            client_ip = client.get("addr")

            #Kill Address
            response = self.client_kill(client_ip)
    
            #Add to Dictionary
            client_track.append((client_ip, response))
            
        return client_track

    def client_multi_connections(self, command="PING", connections=10):
        """Legacy function to show _temp_redis_client usage for opening multiple temp clients simultaneously.
    
        :param connections: Integer of how many temp redis clients to instantiate
        :param function: String of command to run against the server
        :return results: Dictionary with function returns per client opened
        """
        #Scan Results
        results = {}
    
        #Function Per Connection
        for i in xrange(connections):
            client_call = self._temp_redis_client(
                    func=command,
                    hostname=self.hostname, 
                    port=self.port, 
                    password=self.auth_token, 
                    database=0,
                    ssl=self.ssl
            )
    
            #Add to Dict
            results[str(i)] = client_call
    
        return results

    def database_flush(self, db=None):
        """Flush current database.

        :param db: Integer specifying database id to switch connection to
        :return response: Boolean with result of flush operation
        """
        #Get Original DB
        original_db = self.database

        #Change Database
        if db != None:
            response = self.change_database_connection(db)
        
        #Flush Current Database
        flush_response = self.redis_conn.flushdb()
       
        #Change Database to Original
        if db != None:
            response = self.change_database_connection(original_db)

        return flush_response
        
    def database_keys(self, db=None):
        """Gets all keys for the current database.

        :param db: Database id to perform logic against
        :return scan_results: List with database keys 
        """
        #Get Original DB
        original_db = self.database

        #Change Database
        if db != None:
            response = self.change_database_connection(db)
        
        #Scan Database
        scan_response = self.redis_conn.scan()
       
        #Change Database to Original
        if db != None:
            response = self.change_database_connection(original_db)

        return scan_response[1]
   
    def database_keyspace(self, db=None):
        """Gets keyspace information for current database.
        
        :param db: Database id to perform logic against
        :return db_size: Dictionary with number of keys per database in server
        """
        #Get Original DB
        original_db = self.database
        
        #Track Info
        db_size = {}

        #Change Database
        if db != None:
            response = self.change_database_connection(db)
        
        #Get Database Keys
        response = self.redis_conn.info(section="keyspace")

        #Iterate Dbs
        for key in response:
            #Get DB ID and Num of Keys
            tmp_db = key.replace("db", "")
            tmp_keys = response[key]["keys"]

            #Add to Dict
            db_size.update({tmp_db: tmp_keys})

        #Change Database to Original
        if db != None:
            response = self.change_database_connection(original_db)
        
        return db_size

    def database_values(self, db=None):
        """Gets key value pairs from database.

        :param db: Database id to perform logic against
        :return values: Dictionary with keys and their value type, and value 
        """
        #Get Original DB
        original_db = self.database
        
        #Table Values
        values = {}

        #Change Database
        if db != None:
            response = self.change_database_connection(db)
            
        #Scan Database
        response = self.redis_conn.scan()
        db_keys = response[1]

        #Iterate Keys
        for key in db_keys:
            #Get DB Value
            db_value = self._map_key_to_value(key)
            values.update({key: db_value}) 

        #Change Database to Original
        if db != None:
            response = self.change_database_connection(original_db)
        
        return values

    def key_delete(self, key, db=None):
        """Deletes specific key from database.

        :param key: String specifying which key to get
        :param db: Integer specifying database id to switch connection to
        :return key_deleted: Boolean value to show if key was deleted or not
        """
        #Get Original DB
        original_db = self.database

        #Change Database
        if db != None:
            response = self.change_database_connection(db)

        #Delete Key
        delete_response = self.redis_conn.delete(key)
        key_deleted = (delete_response == 1)

        #Change Database to Original
        if db != None:
            response = self.change_database_connection(original_db)

        return key_deleted

    def key_exists(self, key, db=None):
        """Checks if key exists in database.

        :param key: String specifying which key to get
        :param db: Integer specifying database id to switch connection to
        :return key_exists: Boolean to show if key exists or not
        """
        #Get Original DB
        original_db = self.database

        #Change Database
        if db != None:
            response = self.change_database_connection(db)

        #Check if Key Exists
        exists_response = self.redis_conn.exists(key)
        key_exists = (exists_response == 1)

        #Change Database to Original
        if db != None:
            response = self.change_database_connection(original_db)

        return key_exists
        
    def key_get(self, key, db=None):
        """Gets value for a specific key.

        :param key: String specifying which key to get
        :param db: Integer specifying database id to switch connection to
        :return value: String representation with key information
        """
        #Get Original DB
        original_db = self.database

        #Change Database
        if db != None:
            response = self.change_database_connection(db)
        
        #Get Key from Redis
        value = self._map_key_to_value(key)

        #Change Database to Original
        if db != None:
            response = self.change_database_connection(original_db)
        
        return value
    
    def key_metadata(self, key, db=None):
        """Gets metadata for a specific key.

        :param key: String specifying which key to get
        :param db: Integer specifying database id to switch connection to
        :return metadata: Dictionary with key information
        """
        #Template Dictionary
        metadata = {
            "key": key,
            "bytes": None,
            "encoding": None,
            "idle_time": None,
            "references": None,
            "ttl": None,
            "type": None
        }
        
        #Get Original DB
        original_db = self.database

        #Change Database
        if db != None:
            response = self.change_database_connection(db)
        
        #Get Information
        metadata["bytes"] = self.redis_conn.memory_usage(key)
        metadata["encoding"] = self.redis_conn.object("ENCODING", key)
        metadata["idle_time"] = self.redis_conn.object("IDLETIME", key)
        metadata["references"] = self.redis_conn.object("REFCOUNT", key)
        metadata["ttl"] = self.redis_conn.ttl(key)
        metadata["type"] = self.redis_conn.type(key)
            
        #Change Database to Original
        if db != None:
            response = self.change_database_connection(original_db)
        
        return metadata
    
    def key_set(self, key, data, ttl=None, db=None):
        """Sets specific key in database.

        :param key: String specifying which key to get
        :param data: Data to set in redis
        :param ttl: Time to live to set on the new key
        :param db: Integer specifying database id to switch connection to
        :return new_key: Value of the new key you set in redis
        """
        #Get Original DB
        original_db = self.database

        #Change Database
        if db != None:
            response = self.change_database_connection(db)

        #Delete Key if Present
        delete_response = self.key_delete(key)

        #Add String to Database
        if isinstance(data, str):
            response = self.redis_conn.set(key, data)

        #Add Dict as Hash to Database
        if isinstance(data, dict):
            for data_key in data.keys():
                response = self.redis_conn.hset(key, data_key, data[data_key])
        
        #Add Set to Database
        if isinstance(data, set):
            response = self.redis_conn.sadd(key, *data)
        
        #Add Sorted Set(Matrix) or List to Database
        if isinstance(data, list):
            #If Matrix, Add Sorted Set
            if isinstance(data[0], (list, tuple)):
                #Iterate Items and Get Key and Score
                for data_item in data:
                    data_mapping = {data_item[0]: data_item[1]}
                    response = self.redis_conn.zadd(key, data_mapping)
            else:
                response = self.redis_conn.rpush(key, *data)

        #Add TTL
        if isinstance(ttl, int):
            response = self.redis_conn.expire(key, ttl)

        #Get Newly Set Value
        new_key = self.key_get(key)

        #Change Database to Original
        if db != None:
            response = self.change_database_connection(original_db) 

        return new_key
        
    def key_touch(self, key, db=None):
        """Touches a key to reset its OBJECT IDLETIME metric.

        :param key: String specifying which key to get
        :param db: Integer specifying database id to switch connection to
        :return response: Boolean with result from touch call
        """
        #Get Original DB
        original_db = self.database
        
        #Change Database
        if db != None:
            response = self.change_database_connection(db)
        
        #Touch Given Key
        touch_response = self.redis_conn.touch(key)

        #Change Database to Original
        if db != None:
            response = self.change_database_connection(original_db)

        return touch_response

    def server_command(self, command):
        """Allows user to run commands not available in wrapper.

        :param command: Redis command to run on server
        :return response: Data structure from return of API call
        """
        #Run Given Command
        response = self.redis_conn.execute_command(command)
        
        return response

    def server_configuration(self):
        """Waits for background function to finish to serve Cache Parameters.

        :return aws_parameters: List of dictionaries with Cache Parameters
        """
        #Wait For Background Process to Complete
        while self.aws_parameters == None:
            time.sleep(1)

        return self.aws_parameters
   
    def server_database_num(self):
        """Waits for background function to finish to serve the amount of databases on the server.

        :return database_num: Integer showing how many databases_there are
        """
        #Wait For Background Process to Complete
        while self.database_num == None:
            time.sleep(1)

        return self.database_num
    
    def server_flush(self):
        """Flush all databases on server.

        :return response: Boolean with result of flush operation
        """
        #Flush Server
        response = self.redis_conn.flushall()
        
        return response

    def server_info(self, section="all"):
        """Get server information of Redis.

        :return encoded: Dictionary with server information
        """
        #Section to Upper
        info_section = section.upper()

        #Format Info Command
        info_command = "INFO {0}".format(info_section)
    
        #Send Server Command
        response = self.server_command(info_command)
       
        #Parse String into Dictionary
        encoded = RedisWrapper._redis_string_to_dict(response)
        
        return encoded

    def server_keys(self):
        """Gets all keys from all databases in the server.

        :return scans: Dictionary with keys for each database id
        """
        #Original Connection
        original_db = self.database

        #Scan Results
        scans = {}

        #Get Number of Databases
        database_num = self.server_database_num()

        #Get All Keys from Each DB
        for i in xrange(database_num):
            #Change DB Connection
            response = self.change_database_connection(i)

            #Get Keys
            database_keys = self.database_keys()

            #Add to Dict
            scans[str(i)] = database_keys

        #Set Database Back
        self.database = original_db

        return scans

    def server_keyspace(self):
        """Gets keyspace information for current database.

        :return keyspace: Dictionary with keyspace info for database
        """
        #Get Database Keys
        response = self.redis_conn.info(section="keyspace")
        encoded = RedisWrapper._convert(response)

        return encoded
    
    def server_memory_stats(self):
        """Gets memory statistics from server.

        :return memory_info: Dictionary with keys value pairs of memory statistics
        """
        #Get Memory Stats
        response = self.server_command("MEMORY STATS")
  
        #Parse Memory Response
        memory_info = RedisWrapper._redis_arr_to_dict(response)

        return memory_info
    
    def server_monitor(self, timeout=None):
        """Get Monitor output for Redis Cluster.

        :param timeout: Seconds to keep socket alive for getting responses
        :return str: Yields responses from server monitor calls
        """
        #Get New Connection Pool
        redis_pool = redis.ConnectionPool(
                host=self.hostname, 
                port=self.port, 
                db=self.database, 
                password=self.auth_token,
                socket_timeout=timeout,
                connection_class=redis.connection.SSLConnection
        )

        #Get Connection with Monitor Command
        monitor_conn = redis_pool.get_connection("monitor", None)
        
        #Send Monitor Command
        response = monitor_conn.send_command("monitor")
        
        return self._yield_server_stdout(redis_pool, monitor_conn)

    def server_time(self, time_format="%Y-%m-%dT%H:%M:%S.%3N%z", epoch_return=False):
        """Gets the time on the Redis server.

        :param time_format: String with format to use on epoch
        :param epoch_return: Boolean to dictate if epoch is returned over string
        :return date: Time in either formated string or epoch
        """
        #Get Time From Server
        time_tuple = self.redis_conn.time()

        #Return Epoch of Date String
        if epoch_return == True:
            date = time_tuple[0]
        else:
            #Extract Epoch and Build Datetime
            epoch = time.localtime(time_tuple[0])
            date = time.strftime(time_format, epoch)

        return date

    def server_values(self):
        """Gets key value pairs from all databases in server.

        :return all_values: Dictionary of all key value pairs from server
        """
        #Original Connection
        original_db = self.database
        
        #Tracking
        all_values = {}

        #Get Server Keyspace
        keyspace = self.server_keyspace()

        #Get DB IDs
        valid_dbs = [x.replace("db", "") for x in keyspace]

        #Get All Keys from Each DB
        for i in valid_dbs:
            #Change DB Connection
            response = self.change_database_connection(i)

            #Get Keys
            database_keys = self.database_keys()

            #Set New Key
            all_values[str(i)] = {}

            #Add to Dict
            for key in database_keys:
                value = self._map_key_to_value(key)
                all_values[str(i)][key] = value

        #Fill Empty Database Slots
        database_num = self.server_database_num()
        for i in xrange(database_num):
            if all_values.get(str(i), None) == None:
                all_values.update({str(i): []})

        #Set Database Back
        self.database = original_db
        
        return all_values

    def set_random_on_database(self, num=10, prefix="test"):
        """Sets random keys into current database.

        :param num: Integer for the number of keys to set
        :param prefix: String to prefix random keys with
        :return new_pairs: Array of tuples with new key value pairs
        """
        #Tracking Array
        new_pairs = []

        #Prefix Key String
        key_prefix = prefix
    
        #Get Character Sets 
        choice_upper = string.ascii_uppercase
        choice_lower = string.ascii_lowercase
        choice_digits = string.digits

        #Set Random Key Value Pairs
        for i in range(1, num):
            #Get Random key Value
            rand_str = "".join(random.choice(choice_upper + choice_lower) for x in xrange(5))
            
            #Set New Values for Cache
            new_key = "{0}_{1}".format(key_prefix, rand_str)
            new_val = "".join(random.choice(choice_upper + choice_lower + choice_digits) for x in xrange(5))

            #Set Key
            self.redis_conn.set(new_key, new_val)

            #Add to Tracking
            new_pairs.append((new_key, new_val))

        return new_pairs
    
    def set_random_on_server(self, num=10, prefix="test"):
        """Sets random keys into all databases on the server.

        :param num: Integer for the number of keys to set
        :param prefix: String to prefix random keys with
        :return new_pairs: Dictionary with array of tuples with new key value pairs
        """
        #Tracking Array
        new_pairs = {}

        #Prefix Key String
        key_prefix = prefix
    
        #Get Character Sets 
        choice_upper = string.ascii_uppercase
        choice_lower = string.ascii_lowercase
        choice_digits = string.digits

        #Get Original DB
        original_db = self.database
        
        #Get Number of Databases
        database_num = self.server_database_num()

        #Get All Keys from Each DB
        for i in xrange(database_num):
            #Change Database
            response = self.change_database_connection(i)
            
            #Track Key Pairs
            new_pairs[str(i)] = []

            #Set Random Key Value Pairs
            for j in range(1, num):
                #Get Random key Value
                rand_str = "".join(random.choice(choice_upper + choice_lower) for x in xrange(5))
                
                #Set New Values for Cache
                new_key = "{0}_{1}".format(key_prefix, rand_str)
                new_val = "".join(random.choice(choice_upper + choice_lower + choice_digits) for x in xrange(5))

                #Set Key
                self.redis_conn.set(new_key, new_val)

                #Add to Tracking
                new_pairs[str(i)].append((new_key, new_val))

        #Swap Database to Original
        response = self.change_database_connection(original_db)

        return new_pairs

    def _boto3_client(self, **kwargs):
        """Create Boto3 session with profile or credentials.

        :param kwargs.aws_access_key_id: AWS Access Key ID
        :param kwargs.aws_secret_access_key: AWS Secret Access Key
        :param kwargs.aws_session_token: AWS Session Token
        :param kwargs.aws_region: AWS Region
        :return client: Boto3 Client object for Elasticache
        """
        #Get Profile Name
        aws_profile = kwargs.get("aws_profile", None)
        aws_profile = (aws_profile, os.environ.get("AWS_PROFILE"))[aws_profile == None]

        #If Profile is Set, Use That Profile and Return
        if aws_profile != None:
            try:
                session = boto3.Session(profile_name=aws_profile)
            except ProfileNotFound as e:
                session = boto3.Session(region_name=_DEFAULT_REGION)
        else:
            #Get AWS Access Key ID
            aws_access_key_id =  kwargs.get("aws_access_key_id", None)
            aws_access_key_id = (aws_access_key_id, os.environ.get("AWS_ACCESS_KEY_ID"))[aws_access_key_id == None]

            #Get AWS Access Key ID
            aws_secret_access_key =  kwargs.get("aws_secret_access_key", None)
            aws_secret_access_key = (aws_secret_access_key, os.environ.get("AWS_SECRET_ACCESS_KEY"))[aws_secret_access_key == None]
            
            #Get AWS Access Key ID
            aws_session_token =  kwargs.get("aws_session_token", None)
            aws_session_token = (aws_session_token, os.environ.get("AWS_SESSION_TOKEN"))[aws_session_token == None]
            
            #Get AWS Region
            aws_region = kwargs.get("aws_region", None)
            aws_region = (aws_region, os.environ.get("AWS_REGION"))[aws_region == None]

            #Create Session
            if all([aws_access_key_id, aws_secret_access_key, aws_region]):
                session = boto3.Session(
                    aws_access_key_id = aws_access_key_id,
                    aws_secret_access_key = aws_secret_access_key,
                    aws_session_token = aws_session_token,
                    region_name = aws_region
                )
            else:
                session = boto3.Session(region_name=_DEFAULT_REGION)
            
        #Elasticache Client
        client = session.client("elasticache")

        #Ensure Credentials Are Valid
        try:
            response = client.describe_replication_groups(MaxRecords=20)
        except (ClientError, NoCredentialsError) as e:
            client = str(e)
    
        return client

    def _cache_connection_variables(self, hostname, port):
        """Get Redis connection variables from AWS.

        :param hostname: String with Elasticache hostname
        :param port: Integer for port connection
        :return redis_hostname: String with Elasticache hostname
        :return redis_port: Integer for port connection
        """
        #Return if Values are Already Set
        if hostname != None and port != None:
            #Set Values
            redis_hostname = hostname
            redis_port = port

            #Parse AWS Name from Endpoint
            if self.ssl == True:
                self.aws_name = RedisWrapper._ssl_parse_hostname(redis_hostname)
            else:
                self.aws_name = re.sub("\..*", "", redis_hostname)
        else:
            #Fail if Client Failed to Initialize
            if isinstance(self.aws_client, str):
                err_message = "Objects AWS Client failed to instantiate with message: '{0}'".format(self.aws_client)
                raise Exception(err_message)

            #Get Group Name from Object
            replication_group_name = self.aws_name
            
            #Query AWS
            try:
                response = self.aws_client.describe_replication_groups(ReplicationGroupId=replication_group_name)
            except ClientError as e:
                err_message = str(e)
                raise Exception(err_message)

            #Get Replication Group Facts
            redis_facts = response["ReplicationGroups"].pop(0)
            redis_nodes = redis_facts["NodeGroups"].pop(0)
            redis_hostname = redis_nodes["PrimaryEndpoint"]["Address"]
            redis_port = redis_nodes["PrimaryEndpoint"]["Port"]

            #Set to Object
            self.aws_facts = redis_facts
      
        return (redis_hostname, redis_port)

    def _cache_parameters(self, custom_parameter_group=None):
        """Get servers redis.conf from AWS and sets values on object.

        :param custom_parameter_group: String with custom created cache parameter group
        :return: None
        """
        #Hardcode Database Num/Parameters when Client isnt Available
        if isinstance(self.aws_client, str):
            self.aws_parameters = dict()
            self.database_num = 16
            return

        #Get AWS Facts if Not Present
        if self.aws_facts == None:
            response = self.aws_client.describe_replication_groups(ReplicationGroupId=self.aws_name)
            self.aws_facts = response.get("ReplicationGroups").pop(0)

        #Get Redis Version
        redis_info = self.redis_conn.info()
        redis_version = redis_info.get("redis_version")
        redis_is_clustered = redis_info.get("cluster_enabled") > 0

        #Get Redis Cache Parameter Group
        response = self.aws_client.describe_cache_engine_versions(Engine="redis", EngineVersion=redis_version)
        cache_engine = response.get("CacheEngineVersions").pop(0)
        cache_parameter_group = cache_engine.get("CacheParameterGroupFamily")

        #Format AWS Cache Parameter Group Name
        if custom_parameter_group != None:
            redis_parameter_group_name = custom_parameter_group
        if redis_is_clustered == True:
            redis_parameter_group_name = "default.{0}.cluster.on".format(cache_parameter_group)
        else:
            redis_parameter_group_name = "default.{0}".format(cache_parameter_group)

        #Get Cache Parameters
        response = self.aws_client.describe_cache_parameters(CacheParameterGroupName=redis_parameter_group_name)
        cache_parameters = response.get("Parameters")

        #Set Cache Parameter Group
        self.aws_parameters = cache_parameters

        #Get Database Size
        for obj in cache_parameters:
            if obj.get("ParameterName") == "databases":
                self.database_num = int(obj.get("ParameterValue"))
                break

        return None

    def _map_key_to_value(self, key, conn=None):
        """Maps the type of key to the corresponding Redis API call.

        :param key: The key to act on
        :param conn: Use another Redis object to grab keys
        :return key_type: The redis data type of the key
        :return key_value: The value of the key
        """
        #Establish Connection
        conn = (conn, self.redis_conn)[conn == None]

        #Get Key Type
        key_type = conn.type(key).lower()
        key_value = None

        #Get Value by Key Type
        if key_type == "string":
            key_value = conn.get(key)
        elif key_type == "hash":
            key_value = conn.hgetall(key)
        elif key_type == "zset":
            key_value = conn.zrange(key, 0, -1, desc=False, withscores=True)
        elif key_type == "list":
            key_value = conn.lrange(key, 0, -1)
        elif key_type == "set":
            key_value = conn.smembers(key)

        return (key_type, key_value)

    def _redis_client(self):
        """Create Redis client.

        :return redis_conn: Redis connection object
        """
        #Get Redis Client
        redis_conn = redis.Redis(
            host=self.hostname,
            port=self.port,
            password=self.auth_token,
            db=self.database,
            ssl=self.ssl,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=False,
            decode_responses=False
        )

        return redis_conn
    
    def _temp_redis_client(self, **kwargs):
        """Creates temporary Redis client which is killed after executing task.

        :param kwargs.func: String of function of the Redis class you want to run
        :param kwargs.hostname: String of hostname to use for connecting
        :param kwargs.port: Integer port to use for connecting to cache
        :param kwargs.password: String auth token to use for connecting to cache
        :param kwargs.database: Integer database ID to connect to
        :param kwargs.ssl: Boolean whether to use SSL or not
        :return redis_conn: Redis connection object
        """
        #Get Temp Redis Client
        redis_conn = redis.Redis(
            host=kwargs.get("hostname"),
            port=kwargs.get("port"),
            password=kwargs.get("password"),
            db=kwargs.get("database"),
            ssl=kwargs.get("ssl"),
            decode_responses=False
        )

        #Run Function in Temp Connection
        if kwargs.get("func", None) != None:
            #Format Function
            run_func = kwargs.get("func").upper()

            #Make Redis Call
            with redis_conn:
                response = redis_conn.execute_command(run_func)
                return response
        else:
            return True
    
    def _yield_server_stdout(self, pool, connection):
        """Continuously yield redis responses until expected Exceptions occur.

        :param pool: Keepalive ConnectionPool object
        :param connection: Connection continuously grabbing facts from call
        :return str: Responses from redis server
        """
        #Termination Text
        terminate = "Terminated"

        #Yield Until KeyboardInterrupt
        try:
            while True:
                yield connection.read_response()
        except KeyboardInterrupt as e: 
            terminate = "Interrupted"
        except TimeoutError as e:
            terminate = "Timeout"
        finally: 
            response = pool.release(connection)

        yield terminate

    @staticmethod
    def public_methods():
        """Gets all public methods from class.

        :return methods: Array of all publicly available methods
        """
        #Track Methods
        methods = []

        #Get Call Attributes
        class_attributes = dir(RedisWrapper)

        #Iterate Class Attributes
        for attribute in class_attributes:
            #Get Current Object from Class
            class_attr = getattr(RedisWrapper, attribute)

            #Print If Method and Isnt Private
            if (callable(class_attr) == True) and (attribute[0] != "_"):
                methods.append(attribute)

        return methods

    @staticmethod
    def _convert(invar, encoding="utf-8"):
        """Recursively encodes data structures to certain encoding type.

        :param invar: Any data structure
        :param encoding: String with encoding type
        :return invar: Encoded version of data type
        """
        if isinstance(invar, dict):
            return {RedisWrapper._convert(key): RedisWrapper._convert(value) for key, value in invar.iteritems()}
        elif isinstance(invar, list):
            return [RedisWrapper._convert(element) for element in invar]
        elif isinstance(invar, unicode):
            return invar.encode(encoding)
        else:
            return invar

    @staticmethod
    def _redis_arr_to_dict(data):
        """Recursively turns 2 step key pair array to dictionary.

        :param data: Input data structure of either string or list
        :return dictionary: Dictionary with key value pairs
        """
        #Get Dictionary
        dictionary = {}

        #Iterate Through Items
        for i in xrange(0, len(data), 2):
            #Get Data
            iter_key = data[i]
            iter_value = data[i+1]

            #If List, Recurse Key Pairs
            if isinstance(iter_value, list):
                iter_value = RedisWrapper._redis_arr_to_dict(iter_value)
            
            #Add to Dictionary
            dictionary[iter_key] = iter_value

        return dictionary

    @staticmethod
    def _redis_string_to_dict(data):
        """Turn redis return strings into dictionary representations.

        :param data: Input data structure of either string or list
        :return dictionary: Dictionary with key value pairs
        """
        
        #Track Keys
        dictionary = dict()
        parent_key = None
    
        #Split Redis Info Lines
        for line in data.splitlines():
            if (line.isspace() == True) or (len(line) < 1):
                continue
            elif line.find("#") >= 0:
                #Get Alphanumeric Header from String
                section_key = filter(str.isalnum, line)
    
                #Add as New Key in Dict
                dictionary[section_key] = dict()
    
                #Track Last Parent Key
                parent_key = section_key
            else:
                #Get Line Key and Values
                line_key, line_value = line.split(":", 1)
               
                #Handle Key vs Subkey Formats
                if line.find("=") > 0:
                    #Declare New Key
                    dictionary[parent_key][line_key] = dict()
                   
                    #Iterate Sub Element Values
                    for unpacked in line_value.split(","):
                        #Unpack Keys from Delimited List
                        unpacked_key, unpacked_value = unpacked.split("=")
                        
                        #Add To Dictionary
                        dictionary[parent_key][line_key][unpacked_key] = unpacked_value
                else:
                    dictionary[parent_key][line_key] = line_value
    
        return dictionary

    @staticmethod
    def _ssl_parse_hostname(hostname):
        """Parses SSL elasticache hostnames.

        :param hostname: String with Elasticache hostname
        :return aws_name: String of AWS set name
        """
        #Tracking
        aws_name = ""
    
        #Get Index Vars
        index = 1
        start = hostname.find(".")
    
        while True:
            #Temp Vars
            tmp_index = (start + index)
            tmp_char = hostname[tmp_index]
    
            #If Char is Dot, Return
            if tmp_char == ".":
                break
            else:
                aws_name += tmp_char
                index += 1
        
        return aws_name 
