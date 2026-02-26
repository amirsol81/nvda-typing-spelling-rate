# Typing & Spelling Rate: separate speech rates for typing echo and NVDA spelling.
# Copyright (C) 2026
# This file is covered by the GNU General Public License.

from __future__ import annotations

import unicodedata
import json

import globalPluginHandler
import gui
import wx
import config
import api

from gui import guiHelper
from logHandler import log

# Speech internals
import speech as _speechPkg
from speech import speech as _speech
from speech.commands import RateCommand
from config.configFlags import TypingEcho


_ADDON_SECTION = "typingEchoRate"

_originalSpeakTypedCharacters_mod = None  # type: ignore
_originalSpeakTypedCharacters_pkg = None  # type: ignore
_isPatched = False


def _initConfigSpec() -> None:
    """Register config spec for the add-on (safe to call multiple times)."""
    try:
        config.conf.spec[_ADDON_SECTION]
        return
    except Exception:
        pass

    # typingRate is an absolute value (0..100). Default is  -1 (follow NVDA's current speech rate).
    config.conf.spec[_ADDON_SECTION] = {
        "enabled": "boolean(default=True)",
        "enabledSpelling": "boolean(default=True)",
        # Absolute typing rate per synthesizer, stored as compact JSON: {"espeak":72,"eloquence":65,...}
        "typingRatesJson": "string(default=\"\")",
        # Fallback absolute typing rate if no per-synth entry exists; -1 means follow default speech rate.
        "typingRate": "integer(default=-1,min=-1,max=100)",
        # OneCore extra boost per synthesizer (0..100), stored as compact JSON.
        "oneCoreBoostJson": "string(default=\"\" )",
        # Fallback OneCore boost if no per-synth entry exists.
        "oneCoreBoost": "integer(default=0,min=0,max=100)",
        # Absolute spelling rate per synthesizer (used by NVDA's built-in spelling commands), stored as compact JSON.
        "spellingRatesJson": "string(default=\"\")",
        # Fallback absolute spelling rate if no per-synth entry exists; -1 means follow default speech rate.
        "spellingRate": "integer(default=-1,min=-1,max=100)",
        # OneCore extra boost for spelling per synthesizer (0..100), stored as compact JSON.
        "oneCoreSpellBoostJson": "string(default=\"\" )",
        # Fallback OneCore spelling boost if no per-synth entry exists.
        "oneCoreSpellBoost": "integer(default=0,min=0,max=100)",
        # If True, also apply to typed words (not just typed characters).
        "applyToWords": "boolean(default=False)",
    }


def _getConf():
    return config.conf[_ADDON_SECTION]

def _getActiveSynthName() -> str:
    try:
        synth = _speech.getSynth()
        if synth and getattr(synth, "name", None):
            return str(synth.name)
    except Exception:
        pass
    return ""

def _isOneCoreSynthName(name: str) -> bool:
    n = (name or "").lower()
    return "onecore" in n or n == "onecore"

def _getMaxRateForSynth(name: str) -> int:
    # NVDA rate is 0..100 across synths (UI stays consistent).
    return 100


def _loadBoostMap(conf) -> dict:
    raw = conf.get("oneCoreBoostJson", "") or ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                try:
                    out[str(k)] = int(v)
                except Exception:
                    continue
            return out
    except Exception:
        pass
    return {}

def _saveBoostMap(conf, m: dict) -> None:
    try:
        conf["oneCoreBoostJson"] = json.dumps(m, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        conf["oneCoreBoostJson"] = ""


def _loadSpellBoostMap(conf) -> dict:
    raw = conf.get("oneCoreSpellBoostJson", "") or ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                try:
                    out[str(k)] = int(v)
                except Exception:
                    continue
            return out
    except Exception:
        pass
    return {}


def _saveSpellBoostMap(conf, m: dict) -> None:
    try:
        conf["oneCoreSpellBoostJson"] = json.dumps(m, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        conf["oneCoreSpellBoostJson"] = ""

def _getBoostForSynth(conf, synthName: str) -> int:
    m = _loadBoostMap(conf)
    if synthName and synthName in m:
        try:
            return int(m[synthName])
        except Exception:
            return 0
    try:
        return int(conf.get("oneCoreBoost", 0))
    except Exception:
        return 0


def _getSpellBoostForSynth(conf, synthName: str) -> int:
    m = _loadSpellBoostMap(conf)
    if synthName and synthName in m:
        try:
            return int(m[synthName])
        except Exception:
            return 0
    try:
        return int(conf.get("oneCoreSpellBoost", 0))
    except Exception:
        return 0

def _loadTypingRatesMap(conf) -> dict:
    raw = conf.get("typingRatesJson", "") or ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                try:
                    out[str(k)] = int(v)
                except Exception:
                    continue
            return out
    except Exception:
        pass
    return {}

def _saveTypingRatesMap(conf, m: dict) -> None:
    try:
        conf["typingRatesJson"] = json.dumps(m, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        conf["typingRatesJson"] = ""


def _loadSpellingRatesMap(conf) -> dict:
    raw = conf.get("spellingRatesJson", "") or ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                try:
                    out[str(k)] = int(v)
                except Exception:
                    continue
            return out
    except Exception:
        pass
    return {}


def _saveSpellingRatesMap(conf, m: dict) -> None:
    try:
        conf["spellingRatesJson"] = json.dumps(m, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        conf["spellingRatesJson"] = ""

def _getTypingRateForSynth(conf, synthName: str) -> int:
    m = _loadTypingRatesMap(conf)
    if synthName and synthName in m:
        return int(m[synthName])
    try:
        return int(conf.get("typingRate", -1))
    except Exception:
        return -1


def _getSpellingRateForSynth(conf, synthName: str) -> int:
    m = _loadSpellingRatesMap(conf)
    if synthName and synthName in m:
        return int(m[synthName])
    try:
        return int(conf.get("spellingRate", -1))
    except Exception:
        return -1


def _getDefaultSpeechRate() -> int:
    """Return NVDA's current configured speech rate (0..100) for the active synth."""
    try:
        return int(RateCommand().defaultValue)
    except Exception:
        # As a fallback, mirror the common config layout.
        try:
            synth = _speech.getSynth()
            if synth:
                return int(config.conf["speech"][synth.name]["rate"])
        except Exception:
            pass
    return 50



def _computeTypingRateOffset() -> int:
    """Compute offset for typed echo relative to the active synth default rate.

    For OneCore, an additional optional boost is added (0..50) to make changes near the top end
    more noticeable, while keeping the main typing rate slider consistent (0..100).
    """
    conf = _getConf()
    if not conf.get("enabledSpelling", conf.get("enabled", True)):
        return 0

    synthName = _getActiveSynthName()
    defaultRate = _getDefaultSpeechRate()

    typingRate = _getTypingRateForSynth(conf, synthName)
    if typingRate < 0:
        # Follow default speech rate unless a OneCore boost is configured.
        typingRate = defaultRate

    # Clamp typing rate to 0..100.
    if typingRate < 0:
        typingRate = 0
    elif typingRate > 100:
        typingRate = 100

    offset = typingRate - defaultRate

    # Optional OneCore boost (adds extra offset, not an absolute rate).
    if _isOneCoreSynthName(synthName):
        boost = _getBoostForSynth(conf, synthName)
        if boost < 0:
            boost = 0
        elif boost > 100:
            boost = 100
        offset += boost

    return offset


def _computeSpellingRateOffset() -> int:
    """Compute offset for spelling relative to the active synth default rate."""
    conf = _getConf()
    if not conf.get("enabled", True):
        return 0

    synthName = _getActiveSynthName()
    defaultRate = _getDefaultSpeechRate()

    spellingRate = _getSpellingRateForSynth(conf, synthName)
    if spellingRate < 0:
        spellingRate = defaultRate

    if spellingRate < 0:
        spellingRate = 0
    elif spellingRate > 100:
        spellingRate = 100

    offset = spellingRate - defaultRate

    if _isOneCoreSynthName(synthName):
        boost = _getSpellBoostForSynth(conf, synthName)
        if boost < 0:
            boost = 0
        elif boost > 100:
            boost = 100
        offset += boost

    return offset


def _speakWithTypingRate(seq):
    """Speak a prepared speech sequence with optional typing-rate injection."""
    offset = _computeTypingRateOffset()
    if offset == 0:
        _speech.speak(seq)
        return
    # Inject rate change, then restore to default.
    _speech.speak([RateCommand(offset=offset), *seq, RateCommand()])


def _speakSpellingWithTypingRate(text: str) -> None:
    # getSpellingSpeech yields a sequence including EndUtteranceCommand.
    seq = list(_speech.getSpellingSpeech(text))
    _speakWithTypingRate(seq)


def _speakTextWithTypingRate(text: str) -> None:
    # speakText expects a sequence too; we keep it simple.
    _speakWithTypingRate([text])


def _speakSpellingWithSpellingRate(text: str, *args, **kwargs) -> None:
    """Speak spelling with the configured spelling rate.

    Accepts *args/**kwargs to be resilient to NVDA signature changes.
    """
    offset = _computeSpellingRateOffset()
    try:
        seq = list(_speech.getSpellingSpeech(text, *args, **kwargs))
    except TypeError:
        seq = list(_speech.getSpellingSpeech(text))
    if offset == 0:
        _speech.speak(seq)
        return
    _speech.speak([RateCommand(offset=offset), *seq, RateCommand()])


# --- Monkey patch NVDA typing echo ---

_ORIG_speakTypedCharacters_mod = None
_ORIG_speakTypedCharacters_pkg = None
_ORIG_speakSpelling_mod = None
_ORIG_speakSpelling_pkg = None

# Buffer used by NVDA to assemble typed words.
_curWordChars: list[str] = []

PROTECTED_CHAR = "*"
FIRST_NONCONTROL_CHAR = " "


def _clearTypedWordBuffer() -> None:
    _curWordChars.clear()


def _isFocusEditable() -> bool:
    """Check if the currently focused object is editable (roughly matching NVDA core)."""
    try:
        import controlTypes

        obj = api.getFocusObject()
        controls = {
            controlTypes.ROLE_EDITABLETEXT,
            controlTypes.ROLE_DOCUMENT,
            controlTypes.ROLE_TERMINAL,
        }
        return (
            (obj.role in controls or controlTypes.STATE_EDITABLE in obj.states)
            and controlTypes.STATE_READONLY not in obj.states
        )
    except Exception:
        # If anything goes wrong, fail open (don't block echo).
        return True


def _patched_speakTypedCharacters(ch: str):
    """
    Wrap NVDA typing echo and inject an optional typing rate only for typed chars / words.

    This intentionally mirrors NVDA's core behavior closely, while routing the speech calls
    through _speakSpellingWithTypingRate / _speakTextWithTypingRate.
    """
    try:
        typingIsProtected = api.isTypingProtected()
        realChar = PROTECTED_CHAR if typingIsProtected else ch

        # Keep a buffer for typed words.
        if unicodedata.category(ch)[0] in "LMN":
            _curWordChars.append(realChar)
        elif ch == "\b":
            # Backspace.
            del _curWordChars[-1:]
        elif ch == "\u007f":
            # Delete generated in some apps with control+backspace.
            return
        elif len(_curWordChars) > 0:
            typedWord = "".join(_curWordChars)
            _clearTypedWordBuffer()
            if log.isEnabledFor(log.IO):
                log.io("typed word: %s" % typedWord)

            if (not typingIsProtected) and _getConf().get("applyToWords", False):
                typingEchoMode = config.conf["keyboard"]["speakTypedWords"]
                if typingEchoMode != TypingEcho.OFF.value:
                    if typingEchoMode == TypingEcho.ALWAYS.value or (
                        typingEchoMode == TypingEcho.EDIT_CONTROLS.value and _isFocusEditable()
                    ):
                        _speakTextWithTypingRate(typedWord)
            else:
                # fall back to NVDA core for typed words if we are not applying our typing rate
                typingEchoMode = config.conf["keyboard"]["speakTypedWords"]
                if typingEchoMode != TypingEcho.OFF.value and not typingIsProtected:
                    if typingEchoMode == TypingEcho.ALWAYS.value or (
                        typingEchoMode == TypingEcho.EDIT_CONTROLS.value and _isFocusEditable()
                    ):
                        _speech.speakText(typedWord)

        typingEchoMode = config.conf["keyboard"]["speakTypedCharacters"]
        if typingEchoMode != TypingEcho.OFF.value and ch >= FIRST_NONCONTROL_CHAR:
            if typingEchoMode == TypingEcho.ALWAYS.value or (
                typingEchoMode == TypingEcho.EDIT_CONTROLS.value and _isFocusEditable()
            ):
                _speakSpellingWithTypingRate(realChar)
    except Exception:
        log.error("TypingEchoRate: error in patched speakTypedCharacters", exc_info=True)
        # If something goes wrong, try to fall back to NVDA core.
        try:
            orig = _ORIG_speakTypedCharacters_pkg or _ORIG_speakTypedCharacters_mod
            if orig is not None:
                return orig(ch)
        except Exception:
            pass


def _patched_speakSpelling(text: str, *args, **kwargs):
    """Patch NVDA spelling so built-in spelling commands use our spelling rate."""
    try:
        return _speakSpellingWithSpellingRate(text, *args, **kwargs)
    except Exception:
        log.error("TypingEchoRate: error in patched speakSpelling", exc_info=True)
        try:
            orig = _ORIG_speakSpelling_pkg or _ORIG_speakSpelling_mod
            if orig is not None:
                return orig(text, *args, **kwargs)
        except Exception:
            pass


# --- Settings panel ---


class TypingEchoRateSettingsPanel(gui.SettingsPanel):
    # Translators: Title for the add-on settings panel.
    title = _("Typing & Spelling Rate")

    def makeSettings(self, settingsSizer):
        helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

        conf = _getConf()

        self.enableCtrl = helper.addItem(
            wx.CheckBox(self, label=_("Enable separate typing rate"))
        )
        self.enableCtrl.SetValue(bool(conf.get("enabled", True)))

        self.enableSpellCtrl = helper.addItem(
            wx.CheckBox(self, label=_("Enable separate spelling rate"))
        )
        self.enableSpellCtrl.SetValue(bool(conf.get("enabledSpelling", conf.get("enabled", True))))

        self.applyWordsCtrl = helper.addItem(
            wx.CheckBox(self, label=_("Also apply to typed words"))
        )
        self.applyWordsCtrl.SetValue(bool(conf.get("applyToWords", False)))

        # Rate slider (absolute), per synthesizer.
        synthName = _getActiveSynthName()
        defaultRate = _getDefaultSpeechRate()
        maxRate = 100

        currentTypingRate = _getTypingRateForSynth(conf, synthName)
        if currentTypingRate < 0:
            currentTypingRate = defaultRate
        if currentTypingRate > maxRate:
            currentTypingRate = maxRate

        helper.addItem(wx.StaticText(self, label=_("Current synthesizer: {name}").format(name=synthName or "?")))

        labelText = _("Typing rate (absolute, 0-100). Default speech rate is {default}.").format(
            default=defaultRate
        )
        helper.addItem(wx.StaticText(self, label=labelText))
        self.rateSlider = wx.Slider(
            self,
            value=int(currentTypingRate),
            minValue=0,
            maxValue=int(maxRate),
            style=wx.SL_HORIZONTAL,
        )
        # Redundantly apply the range/max to be safe across wx builds.
        self.rateSlider.SetRange(0, int(maxRate))
        try:
            self.rateSlider.SetMax(int(maxRate))
        except Exception:
            pass
        helper.addItem(self.rateSlider)

        # OneCore extra boost (adds extra offset for typed echo to make high-end rate changes more noticeable).
        self._isOneCore = _isOneCoreSynthName(synthName)
        self.boostLabel = wx.StaticText(self, label=_("OneCore extra boost (0-100). Adds extra speed only for typing."))
        self.boostSlider = wx.Slider(self, value=0, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)

        if self._isOneCore:
            currentBoost = _getBoostForSynth(conf, synthName)
            if currentBoost < 0:
                currentBoost = 0
            elif currentBoost > 100:
                currentBoost = 100
            self.boostSlider.SetValue(int(currentBoost))
            helper.addItem(self.boostLabel)
            helper.addItem(self.boostSlider)
        else:
            # Hide boost controls for non-OneCore synths.
            self.boostLabel.Hide()
            self.boostSlider.Hide()

        # --- Spelling rate controls ---
        currentSpellingRate = _getSpellingRateForSynth(conf, synthName)
        if currentSpellingRate < 0:
            currentSpellingRate = defaultRate
        if currentSpellingRate > maxRate:
            currentSpellingRate = maxRate

        helper.addItem(wx.StaticText(self, label=" "))
        helper.addItem(wx.StaticText(self, label=_("Spelling rate (used by NVDA spelling commands)")))

        spellLabelText = _("Spelling rate (absolute, 0-100). Default speech rate is {default}.").format(
            default=defaultRate
        )
        helper.addItem(wx.StaticText(self, label=spellLabelText))
        self.spellRateSlider = wx.Slider(
            self,
            value=int(currentSpellingRate),
            minValue=0,
            maxValue=int(maxRate),
            style=wx.SL_HORIZONTAL,
        )
        self.spellRateSlider.SetRange(0, int(maxRate))
        try:
            self.spellRateSlider.SetMax(int(maxRate))
        except Exception:
            pass
        helper.addItem(self.spellRateSlider)

        self.spellBoostLabel = wx.StaticText(
            self,
            label=_(
                "OneCore extra boost for spelling (0-100). Adds extra speed only for spelling."
            ),
        )
        self.spellBoostSlider = wx.Slider(self, value=0, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)

        if self._isOneCore:
            currentSpellBoost = _getSpellBoostForSynth(conf, synthName)
            if currentSpellBoost < 0:
                currentSpellBoost = 0
            elif currentSpellBoost > 100:
                currentSpellBoost = 100
            self.spellBoostSlider.SetValue(int(currentSpellBoost))
            helper.addItem(self.spellBoostLabel)
            helper.addItem(self.spellBoostSlider)
        else:
            self.spellBoostLabel.Hide()
            self.spellBoostSlider.Hide()

        # Test buttons
        btnSizer = wx.BoxSizer(wx.HORIZONTAL)

        # Translators: Button label in settings to test the typing rate (sample includes characters + words).
        self.testTypingBtn = wx.Button(self, label=_("Test typing"))
        btnSizer.Add(self.testTypingBtn, 0, wx.RIGHT, 8)

        # Translators: Button label in settings to test the spelling rate (sample includes characters + words).
        self.testSpellingBtn = wx.Button(self, label=_("Test spelling"))
        btnSizer.Add(self.testSpellingBtn, 0)

        helper.addItem(btnSizer)

        self.testTypingBtn.Bind(wx.EVT_BUTTON, self.onTestTyping)
        self.testSpellingBtn.Bind(wx.EVT_BUTTON, self.onTestSpelling)

    def _getTypingTestOffsetFromUI(self) -> int:
        if not bool(self.enableCtrl.GetValue()):
            return 0
        try:
            typingRate = int(self.rateSlider.GetValue())
        except Exception:
            return 0
        defaultRate = _getDefaultSpeechRate()
        offset = typingRate - defaultRate
        if getattr(self, "_isOneCore", False):
            try:
                boost = int(self.boostSlider.GetValue())
            except Exception:
                boost = 0
            if boost < 0:
                boost = 0
            elif boost > 100:
                boost = 100
            offset += boost
        return offset

    def _getSpellingTestOffsetFromUI(self) -> int:
        if not bool(self.enableCtrl.GetValue()):
            return 0
        try:
            spellingRate = int(self.spellRateSlider.GetValue())
        except Exception:
            return 0
        defaultRate = _getDefaultSpeechRate()
        offset = spellingRate - defaultRate
        if getattr(self, "_isOneCore", False):
            try:
                boost = int(self.spellBoostSlider.GetValue())
            except Exception:
                boost = 0
            if boost < 0:
                boost = 0
            elif boost > 100:
                boost = 100
            offset += boost
        return offset

    def _buildTestSampleSequence(self):
        # A short, deterministic sample that includes both characters and words.
        # Characters are spoken using NVDA's spelling speech helper for clarity.
        seq = list(_speech.getSpellingSpeech("abc"))
        seq.append(", ")
        seq.append("hello world")
        return seq

    def onTestTyping(self, evt):
        offset = self._getTypingTestOffsetFromUI()
        seq = self._buildTestSampleSequence()
        if offset == 0:
            _speech.speak(seq)
        else:
            _speech.speak([RateCommand(offset=offset), *seq, RateCommand()])

    def onTestSpelling(self, evt):
        offset = self._getSpellingTestOffsetFromUI()
        seq = self._buildTestSampleSequence()
        if offset == 0:
            _speech.speak(seq)
        else:
            _speech.speak([RateCommand(offset=offset), *seq, RateCommand()])

    def onSave(self):
        conf = _getConf()
        conf["enabled"] = bool(self.enableCtrl.GetValue())
        conf["enabledSpelling"] = bool(self.enableSpellCtrl.GetValue())
        conf["applyToWords"] = bool(self.applyWordsCtrl.GetValue())

        synthName = _getActiveSynthName()

        # Typing rate is always 0..100 (absolute).
        try:
            val = int(self.rateSlider.GetValue())
        except Exception:
            val = -1

        if val < 0:
            val = -1
        elif val > 100:
            val = 100

        m = _loadTypingRatesMap(conf)
        if synthName:
            m[synthName] = val
            _saveTypingRatesMap(conf, m)
        else:
            conf["typingRate"] = val

        # Save OneCore extra boost (0..50), per synth.
        if _isOneCoreSynthName(synthName):
            try:
                b = int(self.boostSlider.GetValue())
            except Exception:
                b = 0
            if b < 0:
                b = 0
            elif b > 100:
                b = 100

            bm = _loadBoostMap(conf)
            if synthName:
                bm[synthName] = b
                _saveBoostMap(conf, bm)
            else:
                conf["oneCoreBoost"] = b

        # Spelling rate is always 0..100 (absolute).
        try:
            sval = int(self.spellRateSlider.GetValue())
        except Exception:
            sval = -1

        if sval < 0:
            sval = -1
        elif sval > 100:
            sval = 100

        sm = _loadSpellingRatesMap(conf)
        if synthName:
            sm[synthName] = sval
            _saveSpellingRatesMap(conf, sm)
        else:
            conf["spellingRate"] = sval

        # Save OneCore spelling boost, per synth.
        if _isOneCoreSynthName(synthName):
            try:
                sb = int(self.spellBoostSlider.GetValue())
            except Exception:
                sb = 0
            if sb < 0:
                sb = 0
            elif sb > 100:
                sb = 100

            sbm = _loadSpellBoostMap(conf)
            if synthName:
                sbm[synthName] = sb
                _saveSpellBoostMap(conf, sbm)
            else:
                conf["oneCoreSpellBoost"] = sb



# --- Global plugin ---


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self):
        super().__init__()
        _initConfigSpec()
        self._migrateOldConfigIfNeeded()
        self._patchSpeech()
        gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(
            TypingEchoRateSettingsPanel
        )

    def terminate(self):
        try:
            gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(
                TypingEchoRateSettingsPanel
            )
        except Exception:
            pass
        self._unpatchSpeech()
        super().terminate()

    def _migrateOldConfigIfNeeded(self) -> None:
        """Migrate older config formats into per-synth storage (best-effort, safe to call)."""
        conf = _getConf()

        synthName = _getActiveSynthName()
        m = _loadTypingRatesMap(conf)

        # v0.1.0 used rateOffset; convert to absolute based on current default rate.
        if "rateOffset" in conf and synthName and synthName not in m:
            try:
                offset = int(conf.get("rateOffset", 0))
            except Exception:
                offset = 0
            defaultRate = _getDefaultSpeechRate()
            maxRate = 100
            absRate = defaultRate + offset
            if absRate < 0:
                absRate = 0
            elif absRate > maxRate:
                absRate = maxRate
            m[synthName] = absRate
            _saveTypingRatesMap(conf, m)
            try:
                del conf["rateOffset"]
            except Exception:
                pass

        # v0.1.1 / v0.1.2 stored a single global typingRate; copy it into the active synth if no per-synth value exists.
        try:
            legacyAbs = int(conf.get("typingRate", -1))
        except Exception:
            legacyAbs = -1
        if synthName and synthName not in m and legacyAbs >= 0:
            maxRate = 100
            if legacyAbs > maxRate:
                legacyAbs = maxRate
            m[synthName] = legacyAbs
            _saveTypingRatesMap(conf, m)

    def _patchSpeech(self):
        global _ORIG_speakTypedCharacters_mod, _ORIG_speakTypedCharacters_pkg
        global _ORIG_speakSpelling_mod, _ORIG_speakSpelling_pkg
        if (
            _ORIG_speakTypedCharacters_mod is not None
            or _ORIG_speakTypedCharacters_pkg is not None
            or _ORIG_speakSpelling_mod is not None
            or _ORIG_speakSpelling_pkg is not None
        ):
            return
        try:
            # NVDA exposes speakTypedCharacters in BOTH:
            # 1) speech.speech module (imported here as _speech)
            # 2) speech package namespace (imported here as _speechPkg)
            # Many core modules call the package-level function, so we patch both.
            _ORIG_speakTypedCharacters_mod = _speech.speakTypedCharacters
            _ORIG_speakTypedCharacters_pkg = getattr(_speechPkg, "speakTypedCharacters", None)
            _speech.speakTypedCharacters = _patched_speakTypedCharacters
            if _ORIG_speakTypedCharacters_pkg is not None:
                _speechPkg.speakTypedCharacters = _patched_speakTypedCharacters

            # Patch speakSpelling so NVDA's built-in spelling commands use our spelling rate.
            _ORIG_speakSpelling_mod = getattr(_speech, "speakSpelling", None)
            _ORIG_speakSpelling_pkg = getattr(_speechPkg, "speakSpelling", None)
            if _ORIG_speakSpelling_mod is not None:
                _speech.speakSpelling = _patched_speakSpelling
            if _ORIG_speakSpelling_pkg is not None:
                _speechPkg.speakSpelling = _patched_speakSpelling
        except Exception:
            log.error("TypingEchoRate: failed to patch speakTypedCharacters", exc_info=True)

    def _unpatchSpeech(self):
        global _ORIG_speakTypedCharacters_mod, _ORIG_speakTypedCharacters_pkg
        global _ORIG_speakSpelling_mod, _ORIG_speakSpelling_pkg
        try:
            if _ORIG_speakTypedCharacters_mod is not None:
                _speech.speakTypedCharacters = _ORIG_speakTypedCharacters_mod
        except Exception:
            pass
        try:
            if _ORIG_speakTypedCharacters_pkg is not None:
                _speechPkg.speakTypedCharacters = _ORIG_speakTypedCharacters_pkg
        except Exception:
            pass
        _ORIG_speakTypedCharacters_mod = None
        _ORIG_speakTypedCharacters_pkg = None

        try:
            if _ORIG_speakSpelling_mod is not None:
                _speech.speakSpelling = _ORIG_speakSpelling_mod
        except Exception:
            pass
        try:
            if _ORIG_speakSpelling_pkg is not None:
                _speechPkg.speakSpelling = _ORIG_speakSpelling_pkg
        except Exception:
            pass
        _ORIG_speakSpelling_mod = None
        _ORIG_speakSpelling_pkg = None
