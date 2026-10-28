# Sources and licenses

Original Android application, receiver and MCP adapter were written for this private project. No Tongpin source code was copied.

- JSch fork 2.28.8 — https://github.com/mwiede/jsch — BSD-style license. The exact license texts extracted from the pinned JAR are included here and inside the APK under assets/licenses. The JAR SHA256 is checked against Maven Central during bootstrap.
- Android framework APIs and SDK platform 34 — https://developer.android.com/ — build-time dependency. SDK platform archive checksum verified against Google's repository metadata; android.jar is not included in the source delivery or APK.
- Tongpin Clean was evaluated as a reference for feasibility: https://github.com/linzhi-524/tongpin-clean-public-beta . Its TESTING_PERMISSION.md permits personal non-commercial testing, modification, and deployment with restrictions. The app in this project is an independent implementation using Android MediaSession APIs.
- Build uses existing workspace installations of javac, D8, Apktool and apksig. These tools are not bundled in the source delivery.
