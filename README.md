![ChannelBin for Home Assistant](https://raw.githubusercontent.com/TheForgetfulDev/channelbin-homeassistant/main/images/channelbin-wordmark.png)

# ChannelBin for Home Assistant

A read-only Home Assistant integration for [ChannelBin](https://github.com/TheForgetfulDev/channelbin),
a DVR that records IPTV streams and keeps going when they drop. It polls ChannelBin's status API
every 45 seconds and gives you sensors for what is recording right now, how much disk is left,
whether anything needs attention, when the next scheduled recording starts, and how each of your
provider accounts is doing.

It only reads. There are no services to call and nothing here can start, stop or change a
recording; v1 is sensors only.

## What you get

A ChannelBin device with ten entities, plus one device for each provider account.

### The ChannelBin device

**Sensors**

| Entity | Reports |
|---|---|
| Capturing | Recordings capturing right now |
| Converting | Recordings being converted right now |
| Next recording | When the next scheduled recording starts, with `name`, `channel` and `recording_id` attributes. Reads Unknown when nothing is scheduled, and the attributes stay listed with no value |
| Current recording | The name of the recording capturing right now, with its `recording_id`, `channel`, `account`, `started_at` and `stop_time` as attributes. Any others capturing at the same time are listed in `also_recording`, each with the same fields plus its `name`. Reads None when nothing is capturing |
| Disk free | Free space on the recording directory, shown in GB |
| Disk used | Percent used on that same directory |
| Unread alerts | Unread alert count, with the newest one's `severity`, `title` and `created_at` as attributes |
| Accounts OK | Provider accounts in OK status, with `error_count` and `total` as attributes |
| Accounts with errors | Provider accounts in ERROR status, with `ok_count` and `total` as attributes. An account that is syncing or has never synced is not counted |

**Binary sensors**

| Entity | On when |
|---|---|
| Recording | Anything is capturing |
| Has alerts | Any alert is unread (classed as a problem, so it turns up in Home Assistant's own problem views) |

Home Assistant builds the entity IDs from the device name and each entity's name, so they come out
as `sensor.channelbin_capturing`, `sensor.channelbin_next_recording`,
`binary_sensor.channelbin_recording` and so on. If one of those IDs is already taken, Home
Assistant adds a numeric suffix, so check the device page for the exact list before you write
automations against them.

### One device per provider account

Each provider account in ChannelBin gets its own device, listed under the ChannelBin device and
named after the account.

| Entity | Reports |
|---|---|
| Status | OK, Error, Syncing or Never synced. Automations compare against `ok`, `error`, `syncing` and `unsynced` |
| Last sync | When the account last finished a sync |
| Next sync | When the next sync will actually be attempted. Reads Unknown when syncing is turned off for the account |
| Last error | The account's last sync error, cut to 255 characters. Reads Unknown when there isn't one. Filed under the device's diagnostics |
| Channels | Channels the account has |
| Hidden channels | Channels you have hidden on that account. Filed under diagnostics |
| Connections in use | Connections ChannelBin has open to the provider right now (recordings, health checks and live previews), with the limit it enforces as the `max_connections` attribute |
| Provider expiry | When the provider says the subscription runs out. Xtream accounts only, since an M3U playlist doesn't report one |

The devices follow ChannelBin. A new account gets its device at the next poll. A deleted
account's device is removed along with its entities. Renaming an account renames its device,
and the entity IDs stay the same, so automations keep working. If a leftover device ever does
stay behind, you can delete it from its device page. Home Assistant won't let you delete the
ChannelBin device or a device for an account ChannelBin still has, because the next poll would
just bring it back.

## Requirements

- **ChannelBin 0.21.0 or newer**, reachable from Home Assistant. The Current recording
  sensor's `account` attributes need ChannelBin 0.22.0 or newer and read empty before it.
- **Home Assistant 2024.6.0 or newer.**

## Turn the API on in ChannelBin first

1. In ChannelBin, go to **Settings > Integrations**.
2. Click **Generate key**. The key is shown once, so copy it before you leave the page. Only a
   hash of it is kept.
3. Turn the **Home Assistant integration** switch on. It stays disabled until a key exists, which
   is why the key comes first.

Both halves matter. The status API rejects a request unless the switch is on *and* the key
matches, and it answers the same way either way, so a switch you forgot to turn on looks exactly
like a wrong key.

## Install

### HACS

In Home Assistant, open **HACS**, then the **⋯** menu and **Custom repositories**. Add
`https://github.com/TheForgetfulDev/channelbin-homeassistant` with type **Integration**. Then find
ChannelBin in HACS, **Download** it, and restart Home Assistant.

HACS installs from the latest release here and offers an update when a new one is tagged. This
repository is not in the default HACS store, which is why it is added by hand.

### By hand

Copy `custom_components/channelbin/` from this repository into your Home Assistant configuration
directory, so you end up with `<config>/custom_components/channelbin/`. Restart Home Assistant.

### With git, so `git pull` updates it

If your Home Assistant host has git, clone the repository somewhere in your config directory and
symlink the integration into place:

```bash
cd /config
git clone https://github.com/TheForgetfulDev/channelbin-homeassistant channelbin-repo
ln -s /config/channelbin-repo/custom_components/channelbin /config/custom_components/channelbin
```

Restart Home Assistant. To update later:

```bash
cd /config/channelbin-repo && git pull
```

Restart Home Assistant again after a pull.

## Add the integration

**Settings > Devices & Services > Add Integration**, search for ChannelBin, and enter the host,
port, scheme and the API key you generated. The form repeats the setup steps above and has a
help line under each field.

The form checks the connection before it creates anything, so a wrong host, port or key fails
right there with a message instead of silently at the first poll.

## Where the code lives

The integration is developed in the
[main ChannelBin repository](https://github.com/TheForgetfulDev/channelbin), where its tests run
against the API it polls. This repository is the published copy that HACS installs from. It has
its own version line, and gets a release only when the integration itself changes, so a ChannelBin
release on its own will not show up here as an update.

Bug reports and feature requests for the integration belong on this repository's issue tracker.

## License

MIT, the same as ChannelBin. See [LICENSE](LICENSE).
