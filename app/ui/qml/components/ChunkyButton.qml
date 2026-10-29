import QtQuick
import Theme

// A chunky rounded button standing on a darker 4 px edge. Pressing pushes the face down onto the edge
// and shrinks it to 0.97. Kinds: main (coral, the one main action), quiet, right (mint).
Item {
    id: root
    property string text: ""
    property string kind: "main"
    property bool compact: false
    property bool held: false           // shows the pressed look without a press (the gallery)
    signal clicked()

    readonly property bool down: (area.pressed || held) && enabled
    readonly property color face: !enabled ? Theme.surface2
                                  : kind === "main" ? Theme.accent : kind === "right" ? Theme.right : Theme.surface2
    readonly property color edgeColour: !enabled ? Theme.surface2
                                        : kind === "main" ? Theme.accentEdge
                                        : kind === "right" ? Theme.rightEdge : Theme.border
    readonly property color ink: !enabled ? Theme.muted : kind === "quiet" ? Theme.text : Theme.onColour

    implicitWidth: Math.max(label.implicitWidth + 2 * Theme.space24, compact ? 96 : 120)
    implicitHeight: compact ? 40 : 48
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: if (enabled) root.clicked()
    Keys.onSpacePressed: if (enabled) root.clicked()
    Keys.onReturnPressed: if (enabled) root.clicked()

    scale: down ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }

    // The edge peeks out only below the face; a press covers it.
    Rectangle {
        y: Theme.edge
        width: parent.width
        height: parent.height - Theme.edge
        radius: Theme.radiusMedium
        color: root.edgeColour
    }

    Rectangle {
        width: parent.width
        height: parent.height - Theme.edge
        y: root.down || !root.enabled ? Theme.edge : 0
        radius: Theme.radiusMedium
        color: root.face
        border.width: root.activeFocus ? 2 : 0
        border.color: Theme.text
        Behavior on y { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }

        Text {
            id: label
            anchors.centerIn: parent
            width: Math.min(implicitWidth, parent.width - 2 * Theme.space16)
            text: root.text
            color: root.ink
            font.family: Theme.fontBody
            font.weight: Font.ExtraBold
            font.pixelSize: root.compact ? Theme.size14 : Theme.size16
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        enabled: root.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
