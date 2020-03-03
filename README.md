# Redis Wrapper
#### Overview
* ###### Purpose
    * Class to easily allow user interface to AWS Elasticache Redis Clusters.
* ###### Compatibility
    * Compatible for Python Versions 2.7.
* ###### External Dependencies
    * boto3
    * botocore
    * redis (redis-py)
* ###### Notes
    * Typing from Python to Redis on Sets/Gets is handled.
      * If you require complex data structures to be stored, pickle/jsonify your data and PUT as string.
    * Currently only designed of 'Cluster Mode Disabled' Redis Servers.
    
#### Instantiating the Object
  * ###### Without AWS Credentials...
  ```
  Code:
      redisWrap = RedisWrapper(
          hostname="aws.elasticache.endpoint.amazonaws.com",
          port=6379,
          auth_token="password",
          database=0,
          **redis_request
      )
  Notes:
      - When AWS Credentials are absent, AWS Cache Parameters(redis.conf) cannot be pulled and are thus an empty Dictionary
      - The Database Number when AWS Credentials are absent is defaulted to 16 
  ```
  * ###### With AWS Credentials...
  ```
  Code:
      redisWrap = RedisWrapper(
          aws_name="cache_name",
          auth_token="password",
          database=0,
          **redis_request
      )
  Notes:
      - When AWS Credentials are present, AWS Cache Parameters(redis.conf) will be valid to pull back
      - The Database number will be exact as it is pulled from Cache Node Parameters
  ```
  
#### Code Snippets
  * ###### Calling a Method
    ```
    my_info = redisWrap.server_info()
    ```
  * ###### Using the Monitor Generator
    ```
    for log in redisWrap.server_monitor(timeout=None):
        print(log)
    ```
  * ###### Setting Keys
    ```
    def set_string():
          key = "test"
          data = "value"
          response = redisWrap.key_set(key, data)
          
    def set_list():
          key = "test"
          data = ["one", "two", "three"]
          response = redisWrap.key_set(key, data)
          
    def set_set():
        key = "test"
        data = set(["one", "two", "three"])
        response = redisWrap.key_set(key, data)
        
    def set_sorted_set():
        #Is a list of tuples/list where the first index is the key, and the second index is the keys weight 
        key = "test"
        data = [("one", 1), ("two", 22), ("three", 11)]
        response = redisWrap.key_set(key, data)

    def set_hash():
        key = "test"
        data = {"key_one": "value_one", "key_two": "value_two", "key_three": "value_three"}
        response = redisWrap.key_set(key, data)
    
    def set_with_ttl():
        key = "test"
        data = {"key_one": "value_one", "key_two": "value_two", "key_three": "value_three"}
        response = redisWrap.key_set(key, data, ttl=30)
    ```
  * ###### Getting a Key
    ```
    def get_key():
      key = "test"
      value = redisWrap.key_get(key)
    ```
    
#### Object Parameters    
  * ###### Parameters
    * aws_name
      * String Name of Redis Cache in AWS to find hostname and port for
      * Defaults to None
    * hostname
      * String Hostname of Redis Cache
      * Defaults to None
    * port
      * Integer Port of Redis Cache
      * Defaults to 6379
    * database
      * Integer Database ID to connect to
      * Defaults to 0
    * auth_token
      * String Password to use when authenticating to Redis Cluster
      * Defaults to None
    * ssl 
      * Boolean to use SSL when connecting to Redis Cluster 
      * Defaults to True
    * kwargs[aws_profile]
      * String of AWS Profile to use from ~/.aws/credentials
    * kwargs[aws_access_key_id]
      * String of AWS Account Access Key ID
    * kwargs[aws_secret_access_key]
      * String of AWS Account Secret Access Key
    * kwargs[aws_session_token]
      * String of AWS Account Session Token
    * kwargs[aws_region]
      * String of AWS Region
      
  * ###### Notes
    * If 'aws_name' is provided, it will be used to lookup the hostname and port via AWS API Calls unless 'hostname' and 'port' are both defined
    * Using 'hostname' and 'port' allows you to skip some AWS API Calls improving script speed
    * If 'ssl' is set to True, 'auth_token' will need to be provided
 
#### Object Methods
  * ###### Class Methods
    * change_database_connection
    * client_connected
    * client_connected_num
    * client_kill
    * client_kill_all
    * client_multi_connections
    * database_flush
    * database_keys
    * database_keyspace
    * database_values
    * key_delete
    * key_exists
    * key_get
    * key_metadata
    * key_set
    * key_touch
    * public_methods
    * server_command
    * server_configuration
    * server_database_num
    * server_flush
    * server_info
    * server_keys
    * server_keyspace
    * server_memory_stats
    * server_monitor
    * server_time
    * server_values
    * set_random_on_database
    * set_random_on_server
    
  * ###### Static Methods
    * public_methods
    
#### Method Documentation
  * ###### Class Methods
    ```
    change_database_connection(int: db=None) -> bool
        - Change database connection to specified number.

    client_connected() -> list[dict]
        - Get current clients connected to server.

    client_connected_num() -> int
        - Get number of current clients connected to server.

    client_kill(str: address) -> bool
        - Kills a specific client when given an address.

    client_kill_all() -> bool
        - Kills all clients connected except connection from self.

    client_multi_connections(str: command='PING', int: connections=10) -> dict
        - Legacy function to show _temp_redis_client usage for opening multiple temp clients simultaneously.
        - Could be used for tests if threading is implemented.

    database_flush(int: db=None) -> bool 
        - Flush current database.

    database_keys(int: db=None) -> list[str]
        - Gets all keys for the current database.

    database_keyspace(int: db=None) -> dict 
        - Gets keyspace information for current database.

    database_values(int: db=None) -> dict
        - Gets key value pairs from database.

    key_delete(str: key, int: db=None) -> bool
        - Deletes specific key from database.

    key_exists(str: key, int: db=None) -> bool
        - Checks if key exists in database.

    key_get(str: key, int: db=None) -> object
        - Gets value for a specific key.

    key_metadata(str: key, int: db=None) -> dict
        - Gets metadata for a specific key.

    key_set(str: key, object: data, int: ttl=None, int: db=None) -> object
        - Sets specific key in database.

    key_touch(str: key, int: db=None) -> bool
        - Touches a key to reset its OBJECT IDLETIME metric.

    server_command(str: command) -> str
        - Allows user to run commands not available in wrapper.

    server_configuration() -> list[dict]
        - Waits for background function to finish to serve Cache Parameters.

    server_database_num() -> int
        - Waits for background function to finish to serve the amount of databases on the server.

    server_flush() -> bool
        - Flush all databases on server.

    server_info(section="all") -> dict
        - Get server information of Redis.

    server_keys() -> dict
        - Gets all keys from all databases in the server.

    server_keyspace() -> dict
        - Gets keyspace information for current database.

    server_memory_stats() -> dict
        - Gets memory statistics from server.

    server_monitor(timeout=None) -> str
        - Gets and yields continuous output from all commands being run against the server until timeout or keyboard interrupt

    server_time(str: time_format='%Y-%m-%dT%H:%M:%S.%3N%z', bool: epoch_return=False) -> str
        - Gets the time on the Redis server.

    server_values() -> dict
        - Gets key value pairs from all databases in server.

    set_random_on_database(int: num=10, str: prefix='test') -> list[tuple]
        - Sets random keys into current database.

    set_random_on_server(int: num=10, str: prefix='test') -> dict: list[tuple]
        - Sets random keys into all databases on the server.
    ```
  * ###### Static Methods
    ```
    public_methods() -> list[str]
        - Gets all public methods from class.
    ```
