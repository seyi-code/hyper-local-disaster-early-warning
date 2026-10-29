# MQTT Authentication (production)

## Generate password file

```bash
docker run --rm -v "$(pwd)":/work eclipse-mosquitto:2 \
  mosquitto_passwd -c -b /work/passwd telemetry-broker 'CHANGE_ME_STRONG'
docker run --rm -v "$(pwd)":/work eclipse-mosquitto:2 \
  mosquitto_passwd -b /work/passwd sensor-kampala-01 'sensor-secret-1'
```

## Example ACL

```
user telemetry-broker
topic readwrite sensors/#

user sensor-kampala-01
topic write sensors/wl-kampala-01/#
topic read sensors/wl-kampala-01/#
```

## Enable in mosquitto.conf

```
allow_anonymous false
password_file /mosquitto/config/passwd
acl_file /mosquitto/config/acl
```

Mount the files in docker-compose and set MQTT_USERNAME / MQTT_PASSWORD for the telemetry-broker.
