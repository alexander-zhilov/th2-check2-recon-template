# th2-check2-recon
This is one of the parts of the **th2-check2-recon** component, or *recon* in short. 
*Recon* allows you to compare message streams with each other using specified scenarios called *Rule*. 
This part is called **th2-check2-recon-template**. 
It contains the implementation of the *rules* and the entry point. 
The main logic and everything you need to create a *rule* is contained in the **th2_check2_recon** library from **th2-pypi** Nexus repository.


To implement your *rule*, you need to implement the *Rule* class in a separate file in the directory specified
 in the *rules_package_path* parameter of the *custom* config, inheriting it from 
 the *th2_check2_recon.rule.Rule* class from the core library 
 (an example of implementation can be seen in the demo rules in src/rules).


To implement rule means override:
* **get_name()** - specify the name of *rule* in GUI.
```buildoutcfg
   def get_name(self) -> str:
       return "Rule_demo"
```
* **get_description()** - specify the description of *rule* in GUI.
```buildoutcfg
   def get_description(self) -> str:
       return "Rule_demo is used for demo"
```
* **get_attributes()** - specify required message stream attributes. 
```buildoutcfg
   def get_attributes(self) -> [list]:
       return [
           ['parsed', 'subscribe']
       ]
```
* **description_of_groups()** - specify *message groups* into which messages will be distributed.
 You need to specify the name and type of *message group*.
 The *MessageGroupType.multi* type means that several messages with the same hash can be stored in one *message group*.
 The *MessageGroupType.single* type means that all messages in the group have unique hashes.
```buildoutcfg
   def description_of_groups(self) -> dict:
       return {'ExecutionReport': MessageGroupType.multi,
               'NewOrderSingle': MessageGroupType.single}
```
* **group(message, attributes)** - specify which group to put the incoming message.
```buildoutcfg
   def group(self, message: ReconMessage, attributes: tuple):
       message_type: str = message.proto_message.metadata.message_type
       if message_type not in ['ExecutionReport', 'NewOrderSingle']:
           return
       message.group_id = message_type
       message.group_info['message_type'] = message_type
```
* **hash(message, attributes)** - return computed message hash.
 This hash is used to quickly compare messages.
```buildoutcfg
   def hash(self, message: ReconMessage, attributes: tuple):
       cl_ord_id = message.proto_message.fields['ClOrdID'].simple_value
       message.hash = hash(message.proto_message.fields['ClOrdID'].simple_value)
       message.hash_info['ClOrdID'] = cl_ord_id
```
* **check(messages)** - compares messages in detail. Return *Event* for report in GUI.
```buildoutcfg
   def check(self, messages: [ReconMessage]) -> Event:
       settings = ComparisonSettings()
       compare_result = self.message_comparator.compare(messages[0].proto_message, messages[1].proto_message, settings)
       verification_component = VerificationComponent(compare_result.comparison_result)

       info_for_name = dict()
       for message in messages:
           info_for_name.update(message.hash_info)

       body = EventUtils.create_event_body(verification_component)
       attach_ids = [msg.proto_message.metadata.id for msg in messages]
       return EventUtils.create_event(name=f"Match by '{ReconMessage.get_info(info_for_name)}'",
                                      attached_message_ids=attach_ids,
                                      body=body)
```

The lifecycle of an incoming message is:
1. Comes in *rule* from some kind of *pin*. A record about this is written to *log*.
2. The *group(message, attributes)* method is called for this message. 
It is calculated in which *message group* the message should be placed.
3. The hash of the message is calculated using the *hash(message, attributes)*.
4. Searches for messages with the same hash in other *message groups*.
5. If a message with the same hash is found in each group, *check(messages)* is called for all these messages. 
Depending on the types of *message groups* and their number, 
it will be determined which messages to delete and which to keep.
6. If no similar messages are found, then just add the message to the group.

# Recon configuration

* **recon_name** - name report in GUI.
* **cache_size** - maximum *message group* size.
* **rules_package_path** - directory where *rules* are located.
* **event_batch_max_size** - maximum number of events in one *EventBatch*.
* **event_batch_send_interval** - how often to send *EventBatch* with events.
* **rules** - list of *rule* configurations

# Rule configuration

+ **name** - name of the file containing the rule.
+ **enabled** - should *rule* be used or not.
+ **match_timeout** - time interval between compared messages in seconds.
+ **match_timeout_offset_ns** - time interval between compared messages offset in nanoseconds.

# Installing
To install all the necessary dependencies, you need to install all the packages from **requirements.txt**.
 This can be done with **pip install -r requirements.txt**.
 
# Quick start

The config for a *Recon* with two *rules* will look like this:
```buildoutcfg
apiVersion: th2.exactpro.com/v1
kind: Th2GenericBox
metadata:
  name: recon
spec:
  image-name: some_image_name
  image-version: some_image_version
  type: th2-check2-recon
  custom-config:
    recon_name: Demo_Recon
    cache_size: 5000
    event_batch_max_size: 100
    event_batch_send_interval: 1
    rules_package_path: rules
    rules:
      - name: "rule_demo_1"
        enabled: true
        match_timeout: 10
        match_timeout_offset_ns: 0
        configuration: ""
      - name: "demo_conn1_vs_demo_conn2"
        enabled: true
        match_timeout: 10
        match_timeout_offset_ns: 0
        configuration: ""
      - name: "FIX_vs_DC"
        enabled: true
        match_timeout: 10
        match_timeout_offset_ns: 0
        configuration: ""
      - name: "read_log_vs_conn"
        enabled: true
        match_timeout: 10
        match_timeout_offset_ns: 0
        configuration: ""
      - name: "security_status_log_conn"
        enabled: true
        match_timeout: 10
        match_timeout_offset_ns: 0
        configuration: ""
  pins:
    - name: incoming 
      connection-type: mq
      attributes:
        - parsed
        - subscribe
    - name: to_util
      connection-type: grpc
```

To work, you need to add links for all specified pins. A link to *th2-util* is required.
      
Links config:
```buildoutcfg
apiVersion: th2.exactpro.com/v1
kind: Th2Link
metadata:
  name: from-recon-links
spec:
  boxes-relation:
    router-grpc:
      - name: recon-to-util
        from:
          strategy: filter
          box: recon
          pin: to_util
        to:
          service-class: com.exactpro.th2.util.grpc.MessageComparatorServiceService
          strategy: robin
          box: util
          pin: server

```   
