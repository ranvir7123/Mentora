import QtQuick
import QtMultimedia
import Theme

// This step's seconds of the source video, played inside the panel from our local copy: from `start` to
// `end`, then it stops on the last frame; a tap plays it again. When the copy is missing (or will not
// play), it says so and offers the video in the browser instead, when its link is one that may be opened
// (`canGetVideo`, decided by the bridge). Nothing loads until it is opened.
Item {
    id: root
    property var clip: ({ "state": "none", "file": "", "start": 0, "end": 0, "videoUrl": "" })
    property bool open: false
    property bool muted: false
    property bool canGetVideo: false
    signal getVideo()

    property bool failed: false
    property bool ended: false
    readonly property bool playable: clip.state === "available" && clip.file !== "" && !failed
    readonly property real startMs: clip.start * 1000
    readonly property real endMs: clip.end * 1000

    function fileUrl(path) {
        const p = path.replace(/\\/g, "/")
        return p.charAt(0) === "/" ? "file://" + p : "file:///" + p
    }
    function playFromStart() {
        ended = false
        player.setPosition(startMs)
        player.play()
    }

    onClipChanged: failed = false
    onOpenChanged: if (!open) player.stop()

    implicitWidth: 296
    implicitHeight: screen.height + (playable ? Theme.space8 + bar.height : 0)

    Rectangle {
        id: screen
        width: parent.width
        height: Math.round(width * 9 / 16)
        radius: Theme.radiusMedium
        color: Theme.bg

        Rounded {
            anchors.fill: parent
            visible: root.playable
            VideoOutput {
                id: output
                anchors.fill: parent
                fillMode: VideoOutput.PreserveAspectFit
            }
        }

        // Stopped at the end: a play mark says a tap plays it again.
        Rectangle {
            visible: root.playable && root.ended
            anchors.centerIn: parent
            width: Theme.space48
            height: Theme.space48
            radius: width / 2
            color: Theme.veil
            Glyph {
                anchors.centerIn: parent
                name: "play"
                colour: Theme.text
                size: 24
            }
        }

        MouseArea {
            anchors.fill: parent
            enabled: root.playable
            cursorShape: Qt.PointingHandCursor
            Accessible.role: Accessible.Button
            Accessible.name: "Play the clip again"
            onClicked: root.playFromStart()
        }

        Column {
            visible: !root.playable
            anchors.centerIn: parent
            width: parent.width - 2 * Theme.space16
            spacing: Theme.space12

            Text {
                width: parent.width
                text: root.failed ? "This step's video won't play\non this computer."  // saved, but broken
                                  : "This step's video isn't saved\non this computer."  // two even lines
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
                color: Theme.text
                font.family: Theme.fontBody
                font.pixelSize: Theme.size14
            }

            ChunkyButton {
                visible: root.canGetVideo
                anchors.horizontalCenter: parent.horizontalCenter
                kind: "quiet"
                compact: true
                text: "Get the video"
                onClicked: root.getVideo()
            }
        }
    }

    ProgressBar {
        id: bar
        visible: root.playable
        anchors.top: screen.bottom
        anchors.topMargin: Theme.space8
        width: parent.width
        value: root.endMs > root.startMs ? (player.position - root.startMs) / (root.endMs - root.startMs) : 0
    }

    MediaPlayer {
        id: player
        source: root.open && root.playable ? root.fileUrl(root.clip.file) : ""
        videoOutput: output
        audioOutput: AudioOutput { muted: root.muted }
        onMediaStatusChanged: {
            if (mediaStatus === MediaPlayer.LoadedMedia)
                root.playFromStart()
            else if (mediaStatus === MediaPlayer.InvalidMedia)
                root.failed = true
        }
        onPositionChanged: {
            if (playbackState === MediaPlayer.PlayingState && player.position >= root.endMs) {
                pause()
                root.ended = true
            }
        }
        onErrorOccurred: root.failed = true
    }
}
