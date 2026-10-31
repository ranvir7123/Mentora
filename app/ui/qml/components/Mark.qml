import QtQuick
import Theme

// A few words with a highlighter stroke laid behind them: dark words on a block of colour, as if someone ran
// a marker over them. Used for the words that matter on a screen ("Lesson done!", "Not yet", a course's
// name), never for running text.
Item {
    id: root
    property string text: ""
    property color colour: Theme.accent
    property string family: Theme.fontHeading
    property int weight: Font.ExtraBold
    property int pixelSize: Theme.size20
    property real spacing: 0
    property int maximumLineCount: 1
    readonly property alias label: words

    // The stroke reaches a little past the words on each side, like a marker run on by hand.
    readonly property real padX: Math.round(pixelSize * 0.3)
    readonly property real padY: Math.round(pixelSize * 0.08)

    implicitWidth: words.implicitWidth + 2 * padX
    implicitHeight: words.implicitHeight + 2 * padY
    Accessible.role: Accessible.StaticText
    Accessible.name: text

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSmall
        color: root.colour
    }
    Text {
        id: words
        x: root.padX
        y: root.padY
        width: Math.min(implicitWidth, Math.max(0, root.width - 2 * root.padX))
        text: root.text
        color: Theme.onColour
        elide: Text.ElideRight
        wrapMode: root.maximumLineCount > 1 ? Text.Wrap : Text.NoWrap
        maximumLineCount: root.maximumLineCount
        font.family: root.family
        font.weight: root.weight
        font.pixelSize: root.pixelSize
        font.letterSpacing: root.spacing
    }
}
