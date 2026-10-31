import QtQuick
import Theme
import "../components"

// The steps that took you more than one try, most slips first: which lesson and step, the kind of slip the
// step's check named, how many tries it took, a tip in fixed words and a button to practise that step
// again. A step you have since done right first time says so instead of offering the button. With no
// slips yet, one friendly line says where they will show. Nothing here comes from the AI.
Rectangle {
    id: root
    property var mistakes: []
    signal practise(string lessonId, int stepIndex)

    readonly property real pad: Theme.space24
    readonly property bool wide: width >= 560
    readonly property real sideWidth: 184         // the tries and the button, on a wide card

    implicitHeight: words.implicitHeight + 2 * pad
    radius: Theme.radiusLarge
    color: Theme.surface1

    Column {
        id: words
        x: root.pad
        y: root.pad
        width: parent.width - 2 * root.pad
        spacing: Theme.space16

        // The heading, with where the mistakes come from at the other end of the line.
        Item {
            width: parent.width
            height: heading.implicitHeight
            Text {
                id: heading
                text: "Your common mistakes"
                color: Theme.text
                font.family: Theme.fontHeading
                font.weight: Font.ExtraBold
                font.pixelSize: Theme.size20
            }
            Text {
                anchors.right: parent.right
                anchors.left: heading.right
                anchors.leftMargin: Theme.space12
                anchors.baseline: heading.baseline
                horizontalAlignment: Text.AlignRight
                text: "From your checks"
                elide: Text.ElideRight
                color: Theme.muted
                font.family: Theme.fontBody
                font.pixelSize: Theme.size12
            }
        }

        Text {
            visible: root.mistakes.length === 0
            width: parent.width
            text: "No mistakes yet. Steps that take a few tries show up here, with a tip."
            wrapMode: Text.Wrap
            lineHeight: 1.15
            color: Theme.muted
            font.family: Theme.fontBody
            font.pixelSize: Theme.size16
        }

        Repeater {
            model: root.mistakes

            // One step. Wide: what went wrong on the left, the tries and the button on the right. Narrow: the
            // tries and the button go under the words.
            Rectangle {
                id: slip
                required property var modelData
                readonly property bool fixed: modelData.fixed === true
                readonly property real inside: width - 2 * Theme.space16

                width: words.width
                height: (root.wide ? Math.max(info.implicitHeight, side.implicitHeight)
                                   : info.implicitHeight + Theme.space12 + side.implicitHeight) + 2 * Theme.space16
                radius: Theme.radiusMedium
                color: Theme.clear                // an outline, so the quiet button's face stands out on it
                border.width: 2
                border.color: Theme.border

                Column {
                    id: info
                    x: Theme.space16
                    y: Theme.space16
                    width: root.wide ? slip.inside - root.sideWidth - Theme.space24 : slip.inside
                    spacing: Theme.space8

                    // Which lesson and step, with the course's colour.
                    Item {
                        width: parent.width
                        height: where.implicitHeight
                        Rectangle {
                            id: dot
                            anchors.verticalCenter: parent.verticalCenter
                            width: Theme.space8
                            height: Theme.space8
                            radius: Theme.radiusSmall
                            color: Theme.course(slip.modelData.colour || "")
                        }
                        Text {
                            id: where
                            anchors.left: dot.right
                            anchors.leftMargin: Theme.space8
                            anchors.right: parent.right
                            text: (slip.modelData.lessonTitle || "") + ", step " + (slip.modelData.stepIndex + 1)
                            elide: Text.ElideRight
                            color: Theme.muted
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.size12
                        }
                    }

                    Text {
                        width: parent.width
                        text: slip.modelData.instruction || ""
                        wrapMode: Text.Wrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                        color: Theme.text
                        font.family: Theme.fontBody
                        font.weight: Font.Bold
                        font.pixelSize: Theme.size16
                    }

                    Text {
                        visible: text !== ""
                        width: parent.width
                        text: slip.modelData.kind || ""
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        color: slip.fixed ? Theme.muted : Theme.notYet
                        font.family: Theme.fontBody
                        font.weight: Font.Bold
                        font.pixelSize: Theme.size14
                    }

                    Text {
                        width: parent.width
                        text: slip.modelData.tip || ""
                        wrapMode: Text.Wrap
                        lineHeight: 1.15
                        color: Theme.text
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.size14
                    }
                }

                // How many tries it took, and the way to practise it; or, once got right, a tick.
                Column {
                    id: side
                    x: root.wide ? slip.width - Theme.space16 - width : Theme.space16
                    y: root.wide ? (slip.height - implicitHeight) / 2 : info.y + info.implicitHeight + Theme.space12
                    width: root.wide ? root.sideWidth : slip.inside
                    spacing: Theme.space8

                    Text {
                        visible: !slip.fixed
                        width: parent.width
                        horizontalAlignment: root.wide ? Text.AlignRight : Text.AlignLeft
                        text: slip.modelData.times > 1
                              ? "Tricky " + slip.modelData.times + " times,\nup to " + slip.modelData.tries + " tries"
                              : "Took " + slip.modelData.tries + " tries"
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        color: Theme.muted
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.size14
                    }

                    ChunkyButton {
                        visible: !slip.fixed
                        width: root.wide ? parent.width : implicitWidth
                        compact: true
                        kind: "quiet"
                        text: "Practise this again"
                        onClicked: root.practise(slip.modelData.lessonId, slip.modelData.stepIndex)
                    }

                    Row {
                        visible: slip.fixed
                        anchors.right: root.wide ? parent.right : undefined
                        spacing: Theme.space8
                        Glyph {
                            anchors.verticalCenter: parent.verticalCenter
                            name: "tick"
                            size: 16
                            colour: Theme.right
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Got it right last time"
                            color: Theme.right
                            font.family: Theme.fontBody
                            font.weight: Font.Bold
                            font.pixelSize: Theme.size14
                        }
                    }
                }
            }
        }
    }
}
