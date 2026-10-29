import QtQuick
import QtQuick.Shapes
import Theme

// The streak: a gold flame and the number of days in a row. With no streak yet it is a quiet outline.
Row {
    id: root
    property int days: 0
    property real size: 28

    readonly property bool lit: days > 0

    spacing: Theme.space4
    Accessible.role: Accessible.StaticText
    Accessible.name: days === 1 ? "1 day in a row" : days + " days in a row"

    Item {
        width: root.size
        height: root.size
        anchors.verticalCenter: parent.verticalCenter

        Shape {
            width: 24
            height: 24
            scale: root.size / 24
            transformOrigin: Item.TopLeft
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                fillColor: root.lit ? Theme.reward : Theme.clear
                strokeColor: root.lit ? Theme.clear : Theme.muted
                strokeWidth: root.lit ? -1 : 2
                joinStyle: ShapePath.RoundJoin
                PathSvg {
                    path: "M12 2 C12.8 5.6 17.6 8.4 18 13.6 C18.4 18.4 15.4 22 12 22 C8.6 22 5.6 18.8 6 14.6 "
                          + "C6.3 11.6 8.2 9.8 9.4 8 C9.8 10 10.6 11.2 11.8 11.6 C11.2 8.4 11 5 12 2 Z"
                }
            }
            ShapePath {
                fillColor: root.lit ? Theme.rewardEdge : Theme.clear
                strokeColor: Theme.clear
                strokeWidth: -1
                PathSvg {
                    path: "M12 13 C13.6 14.6 15 16 14.8 18 C14.6 19.8 13.4 20.8 12 20.8 "
                          + "C10.6 20.8 9.3 19.8 9.3 18.2 C9.3 16.6 10.8 15.6 12 13 Z"
                }
            }
        }
    }

    Text {
        anchors.verticalCenter: parent.verticalCenter
        text: root.days
        color: root.lit ? Theme.reward : Theme.muted
        font.family: Theme.fontBody
        font.weight: Font.ExtraBold
        font.pixelSize: Theme.size20
    }
}
