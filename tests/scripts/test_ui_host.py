"""Tests for the trimming that turns Flet's client into the UI-test host."""

import pytest

from scripts.ui_host import JNI_LIFTED, trim_main, trim_pubspec

MAIN = """\
import 'package:flet/flet.dart';
import 'package:flet_ads/flet_ads.dart' as flet_ads;
// --FAT_CLIENT_START--
import 'package:flet_audio/flet_audio.dart' as flet_audio;
// --FAT_CLIENT_END--
import 'package:flet_color_pickers/flet_color_pickers.dart'
    as flet_color_picker;
import "package:flet_flashlight/flet_flashlight.dart" as flet_flashlight;
import 'package:flutter/material.dart';

  List<FletExtension> extensions = [
    flet_ads.Extension(),
    flet_color_picker.Extension(),
    // --FAT_CLIENT_START--
    flet_audio.Extension(),
    // --FAT_CLIENT_END--
  ];
"""

PUBSPEC = """\
dependencies:
  flutter:
    sdk: flutter
  flet_ads:
    path: ../sdk/python/packages/flet-ads/src/flutter/flet_ads

# --FAT_CLIENT_START--
  flet_audio:
    path: ../sdk/python/packages/flet-audio/src/flutter/flet_audio
# --FAT_CLIENT_END--
  integration_test:
    sdk: flutter

dependency_overrides:
  flet:
    path: ../packages/flet
  jni: 1.0.0
"""


def test_trim_main_keeps_flet_and_drops_every_extension():
    trimmed = trim_main(MAIN)

    assert "import 'package:flet/flet.dart';" in trimmed
    assert "import 'package:flutter/material.dart';" in trimmed
    assert "flet_" not in trimmed
    assert "Extension()" not in trimmed


def test_trim_pubspec_drops_extensions_and_lifts_jni():
    trimmed = trim_pubspec(PUBSPEC)

    assert "../sdk/" not in trimmed
    assert "path: ../packages/flet" in trimmed
    assert JNI_LIFTED in trimmed
    assert "jni: 1.0.0" not in trimmed


def test_trim_pubspec_fails_on_an_extension_it_cannot_remove():
    with pytest.raises(ValueError, match="../sdk/"):
        trim_pubspec("dependencies:\n  flet_x: {path: ../sdk/x}\n")
