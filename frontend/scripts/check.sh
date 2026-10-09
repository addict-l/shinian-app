#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
xcrun swiftc AIMemoirs/Networking/APIClient.swift scripts/NetworkBoundaryChecks.swift -o /tmp/ai-memories-network-checks
/tmp/ai-memories-network-checks
# State tests use the iOS target because the real adapter handles UIKit photo data.
xcodebuild -project AIMemoirs.xcodeproj -scheme AIMemoirs -configuration Debug \
  -destination "${AI_MEMORIES_TEST_DESTINATION:-platform=iOS Simulator,name=AI Memories UI Check}" \
  CODE_SIGNING_ALLOWED=NO -parallel-testing-enabled NO -only-testing:AIMemoirsTests test
