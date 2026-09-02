# medisana-ha

A Home Assistant **custom integration** for Medisana BS410/A45/BS430/BS440/BS444/BS550
Bluetooth body-composition scales (and other compatible Medisana scales). It's
not limited to the BS444 — any scale that speaks the same Medisana BLE
protocol (identified by the `000078b2-...` GATT service) should work.

## Why this exists

The existing [ESPHome `medisana_bs444` external
component](https://github.com/bwynants/weegschaal) requires a single ESP32 with
a `ble_client` dedicated to actively connecting to the scale. That means:

* the scale can only ever be reached by that one ESP32, and
* if that ESP32 goes offline, all data collection stops.

This integration instead performs the active BLE (GATT) connection **from Home
Assistant itself**, using the built-in [`bluetooth`
integration](https://www.home-assistant.io/integrations/bluetooth/). Home
Assistant automatically picks whichever local Bluetooth adapter or connectable
[Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html) (any
number of them) currently has the best signal to the scale, and transparently
fails over to another one if it becomes unavailable. This gives you:

1. A scale that shows up as its own device in Home Assistant.
2. Automatic failover between any number of ESPHome Bluetooth proxies (or a
   local adapter) — whichever one hears the scale's advertisement services the
   connection.

## How it works

The scale only advertises/accepts a connection briefly after someone steps on
it. This integration listens for that advertisement via Home Assistant's
`bluetooth` integration and, once seen, connects to the scale (through
whichever adapter/proxy currently has it), subscribes to notifications for its
person/weight/body-composition characteristics, tells the scale the current
time, and waits for it to send its data and disconnect. The BLE protocol
implementation (service/characteristic UUIDs, payload decoding, and the
1/1/2010 time-offset quirk of the BS410/A45/BS444) is a Python port of the logic in
the ESPHome `medisana_bs444` component, which itself is based on reverse
engineering work from https://github.com/keptenkurk/BS440.

## Installation

### Option A: HACS (recommended)

[HACS](https://hacs.xyz/) doesn't (yet) list this integration in its default
store, so add it as a **custom repository**:

1. In Home Assistant, open **HACS → Integrations**.
2. Click the **⋮** menu (top right) → **Custom repositories**.
3. Add `https://github.com/drakarah/medisana-ha` as the repository URL, and
   choose **Integration** as the category.
4. Find **Medisana Bluetooth Scale** in HACS and click **Download**.
5. Restart Home Assistant.

### Option B: Manual install

1. Copy the `custom_components/medisana_bs444` folder from this repository
   into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

### After installing (either option)

1. Make sure at least one Bluetooth adapter or ESPHome Bluetooth proxy
   (`bluetooth_proxy` with `active: true`) is set up and in range of the
   scale.
2. Step on the scale once so it advertises. Home Assistant should
   automatically discover it (**Settings → Devices & Services**); alternatively
   add it manually via **Add Integration → Medisana Bluetooth Scale**.
3. During setup, enable **Use time offset** for BS410, A45 and BS444 scales
   (this matches the ESPHome component's `timeoffset: true` option).

## Entities

For each of the up to 8 user "slots" the scale supports, the integration
creates (initially enabled only for user 1 — enable additional users'
entities as needed):

* Sensors: weight, BMI, kcal, fat %, water %, muscle %, bone (kg), age, size,
  sex (diagnostic, disabled by default).
* Binary sensors (diagnostic, disabled by default): high activity.

## Compatibility

Confirmed to work with the same protocol as: A45, BS410, BS430, BS440, BS444,
BS550. Likely compatible with other Medisana scales using the same GATT
service (`000078b2-...`), regardless of what the integration's name suggests.
