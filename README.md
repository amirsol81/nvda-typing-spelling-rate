# Typing & Spelling Rate

**Author:** Amir Soleimani  
**NVDA compatibility:** 2026.1 and later

## What this add-on does

This add-on lets you set a faster (or slower) speech rate specifically for:

- **Typing echo** (characters and words), and
- **Spelling** (spelling output spoken by NVDA).

These rates are independent from your normal synthesizer rate. Your main speech rate is not changed.

## Why this add-on exists

Many users prefer a comfortable speech rate for general reading and navigation, but want a higher rate for rapid typing feedback or spelling—especially when editing text. NVDA's standard speech rate is global, so changing it affects everything. This add-on provides separate rates so you can keep your normal rate while still getting fast, crisp feedback when you type or spell.

## How it works (technical note)

NVDA speaks using a sequence of speech commands. This add-on injects a `RateCommand` into the speech sequence *only for the specific typing/spelling utterance*. It does **not** change the synthesizer's global rate setting, which helps keep the behavior stable and compatible with other add-ons.

## Settings

Open NVDA Settings and locate the add-on's settings panel under the **Typing & Spelling Rate** panel.

### Enable separate typing rate

When checked, the add-on applies your configured typing rate to typing echo output. When unchecked, typing echo uses your normal synthesizer rate.

### Enable separate spelling rate

When checked, the add-on applies your configured spelling rate to spelling output. When unchecked, spelling uses your normal synthesizer rate.

### Typing rate

Adjusts the rate used for typing echo (characters and words) when *Enable separate typing rate* is checked.

### Also apply to typed words

When checked, the typing rate is applied to both typed **characters** and typed **words**. When unchecked, the typing rate is applied only to typed characters.

### Spelling rate

Adjusts the rate used for spelling output when *Enable separate spelling rate* is checked.

### Windows OneCore: Boost

If your synthesizer is **Windows OneCore**, the add-on provides an extra **Boost** option. OneCore can behave differently at high rates, so Boost gives additional headroom without changing NVDA's global rate slider range.

- **Boost range:** 0–100
- **Boost is only used with Windows OneCore.** It has no effect with other synthesizers.

### Test buttons

The panel includes two test buttons:

- **Test typing**: speaks a short sample using the typing rate settings.
- **Test spelling**: speaks a short sample using the spelling rate settings.

The sample includes both characters and words (for example: `A B C, hello world`) so you can judge the rate quickly.

## Notes

- This add-on targets NVDA 2026.1+ (64-bit).
- Settings are stored per synthesizer, so different synthesizers can have different typing/spelling rates.
