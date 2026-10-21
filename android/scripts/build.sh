#!/bin/bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
java_candidates=(
  "${JAVA_HOME:-}"
  "$HOME/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home"
  "/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
  "/Applications/IntelliJ IDEA.app/Contents/jbr/Contents/Home"
  "/Applications/Android Studio.app/Contents/jbr/Contents/Home"
)
resolved_java=""
for candidate in "${java_candidates[@]}"; do
  if [[ -n "$candidate" && -x "$candidate/bin/java" && -x "$candidate/bin/javac" && -x "$candidate/bin/jlink" ]]; then
    java_version="$("$candidate/bin/java" -version 2>&1 | head -n 1)"
    if [[ "$java_version" =~ \"(1[7-9]|2[0-3])\. ]]; then
      resolved_java="$candidate"
      break
    fi
  fi
done
if [[ -z "$resolved_java" ]]; then
  discovered_java="$(/usr/libexec/java_home -v 21 2>/dev/null || true)"
  if [[ -n "$discovered_java" ]]; then resolved_java="$discovered_java"; fi
fi
if [[ -z "$resolved_java" ]]; then
  echo "需要 JDK 17–23（推荐 21）。请设置 JAVA_HOME 后重试。" >&2
  exit 1
fi
export JAVA_HOME="$resolved_java"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
cd "$project_root"
if [[ ! -d "$ANDROID_HOME/platforms/android-36" ]]; then
  echo "需要 Android SDK Platform 36。请在 Android Studio SDK Manager 安装。" >&2
  exit 1
fi
if [[ $# -eq 0 ]]; then set -- :app:assembleDebug :app:testDebugUnitTest :app:lintDebug; fi
exec ./gradlew --console=plain "$@"
