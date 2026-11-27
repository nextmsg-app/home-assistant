# NextMsg for Home Assistant

Send Home Assistant notifications to your phone with [NextMsg](https://nextmsg.app), the one-way push notification app for iPhone and Android. No account: the app gives you a send key, or a pairing code to connect Home Assistant with.

- Set up in the UI with a pairing code from the app; Home Assistant gets its own key that you can revoke in the app at any time
- One notify entity per channel (`notify.nextmsg_home`, `notify.nextmsg_security`, …); each channel is its own tab in the app
- Works with the standard **Notifications: Send a notification message** action (`notify.send_message`), including a title
- If the key is revoked, Home Assistant asks you to pair again

Needs Home Assistant 2026.10 or later and the NextMsg app 1.4 or later ([App Store](https://apps.apple.com/app/nextmsg-push-notifications/id6831546010), [Google Play](https://play.google.com/store/apps/details?id=app.nextmsg)).

![NextMsg demo: push notifications to your phone and pairing with a code](https://raw.githubusercontent.com/nextmsg-app/mcp/main/assets/demo.gif)

## Install

With [HACS](https://hacs.xyz):

1. **HACS → ⋮ → Custom repositories**, add `https://github.com/nextmsg-app/home-assistant` with the type **Integration**
2. Search for **NextMsg** in HACS, download it, and restart Home Assistant

Or by hand: copy `custom_components/nextmsg` into your `config/custom_components/` folder and restart.

## Set up

1. **Settings → Devices & services → Add integration → NextMsg**
2. Choose **Use a pairing code from the app**
3. In the NextMsg app, open **Settings → Send keys → Add send key → Use a pairing code** (older versions: **Connect with a code**) and enter the code it shows (it works once, for 5 minutes)
4. Pick a channel name, like `home`

Home Assistant now shows in the app's list of send keys, where you can rename or revoke it. You can also choose **Enter a key** and paste a send key from the app (**Settings → Send keys → Add send key → Copy a key** makes one just for Home Assistant); a short test message checks it.

To add more channels: open the NextMsg integration and choose **Add channel**.

## Use it

```yaml
actions:
  - action: notify.send_message
    target:
      entity_id: notify.nextmsg_home
    data:
      title: Garage
      message: "The door has been open for 10 minutes"
```

The title is shown in bold on the first line. Messages are up to 640 characters and can use `**bold**`, `*italic*`, `~~strikethrough~~` and `` `code` ``.

If a message can't be sent, the action fails with the reason: an invalid message, the 100 free messages a month used up (Pro in the app removes the limit), or no connection to NextMsg.

## Privacy

Home Assistant sends your messages to `api.nextmsg.app` over HTTPS, with the key in the `Authorization` header. Nothing else is sent: no states, no location, no analytics. See the [privacy policy](https://nextmsg.app/privacy).

## Without this integration

A single `rest_command` works too, with nothing to install: see the [Home Assistant guide](https://nextmsg.app/guides/home-assistant).

## Development

```sh
uv sync --group test
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Tests run against the oldest supported Home Assistant (`pytest-homeassistant-custom-component`). CI also runs `hassfest` and the HACS checks.

## License

MIT
