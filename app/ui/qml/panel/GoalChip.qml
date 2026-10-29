import QtQuick
import Theme
import "../components"

// The goal folded to one line, one tap from opening again. As wide as its words, up to `maxWidth`.
Item {
    id: root
    property string sentence: ""
    property real maxWidth: 264
    signal open()

    implicitWidth: Math.min(maxWidth, Theme.space16 + flag.width + Theme.space8 + words.implicitWidth + Theme.space16)
    implicitHeight: 40
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: "Show your goal: " + sentence
    Accessible.onPressAction: root.open()
    Keys.onSpacePressed: root.open()
    Keys.onReturnPressed: root.open()

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Theme.surface1
        border.width: root.activeFocus ? 2 : 0
        border.color: Theme.text
    }

    Glyph {
        id: flag
        x: Theme.space16
        anchors.verticalCenter: parent.verticalCenter
        name: "flag"
        colour: Theme.muted
        size: 20
        stroke: 2.4
    }

    Text {
        id: words
        x: flag.x + flag.width + Theme.space8
        width: parent.width - x - Theme.space16
        anchors.verticalCenter: parent.verticalCenter
        text: root.sentence
        elide: Text.ElideRight
        maximumLineCount: 1
        color: Theme.text
        font.family: Theme.fontBody
        font.weight: Font.Bold
        font.pixelSize: Theme.size14
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.open()
    }
}
