import QtQuick
import QtQuick.Shapes
import Theme

// Our mascot: a round coral character with a curl on top, a darker belly and two eyes that follow
// `lookAt`. Drawn on a 48 unit grid and scaled to `size`. Only position, scale, rotation and opacity move.
//   resting   breathes slowly and blinks now and then
//   flying    stretches along `heading`, the direction it travels (by at most 12%), and looks that way
//   watching  holds still with its eyes on `lookAt`
//   thinking  looks up, with three dots taking turns beside it
//   cheering  one springy hop, curl up, happy eyes
// `landed` fires once a flight has settled, so the pointer knows when to start talking.
Item {
    id: root
    property real size: 48
    property var lookAt: null           // a point in the window's coordinates; null looks ahead
    property real heading: 0            // degrees, 0 = to the right, clockwise like rotation
    property bool dotsLeft: false       // the thinking dots go on the left, away from a target on the right
    signal landed()

    states: [
        State { name: "resting" }, State { name: "flying" }, State { name: "watching" },
        State { name: "thinking" }, State { name: "cheering" }
    ]
    state: "resting"

    readonly property real stretch: state === "flying" ? 1.12 : 1
    readonly property real reach: 2.5   // how far a pupil can move from the middle of its eye

    // Where the pupils point, as a direction of length 1 (or none).
    readonly property point gaze: {
        if (state === "thinking")
            return Qt.point(-0.35, -0.94)
        if (state === "flying")
            return Qt.point(Math.cos(heading * Math.PI / 180), Math.sin(heading * Math.PI / 180))
        if (!lookAt)
            return Qt.point(0, 0)
        root.x; root.y                  // look again whenever the mascot moves
        const centre = root.mapToItem(null, width / 2, height / 2)
        const dx = lookAt.x - centre.x, dy = lookAt.y - centre.y, far = Math.hypot(dx, dy)
        return far < 1 ? Qt.point(0, 0) : Qt.point(dx / far, dy / far)
    }

    implicitWidth: size
    implicitHeight: size
    Accessible.ignored: true

    // A filled oval drawn as a curve, so its edge stays smooth at any size.
    component Oval: Shape {
        property real cx
        property real cy
        property real rx
        property real ry
        property color fill
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: fill
            strokeColor: Theme.clear
            strokeWidth: -1
            PathAngleArc { centerX: cx; centerY: cy; radiusX: rx; radiusY: ry; startAngle: 0; sweepAngle: 360 }
        }
    }

    property string _was: "resting"
    onStateChanged: {
        if (_was === "flying" && state !== "flying")
            settle.restart()
        if (state === "cheering")
            hop.restart()
        _was = state
    }
    Timer { id: settle; interval: 200; onTriggered: root.landed() }

    Item {
        id: grid
        width: 48
        height: 48
        scale: root.size / 48
        transformOrigin: Item.TopLeft

        Item {
            id: hopper
            anchors.fill: parent

            SequentialAnimation {
                id: hop
                NumberAnimation { target: hopper; property: "y"; to: -14; duration: 160; easing.type: Easing.OutQuad }
                NumberAnimation { target: hopper; property: "y"; to: 0; duration: 260; easing.type: Easing.OutBack; easing.overshoot: 2.2 }
            }

            Item {
                id: breather
                anchors.fill: parent
                transformOrigin: Item.Bottom
                SequentialAnimation on scale {
                    running: root.state === "resting" && root.visible
                    loops: Animation.Infinite
                    NumberAnimation { to: 1.03; duration: 1200; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1; duration: 1200; easing.type: Easing.InOutSine }
                    onRunningChanged: if (!running) breather.scale = 1
                }

                // Turned to the heading, stretched along it, then the face turned back upright.
                Item {
                    anchors.fill: parent
                    rotation: root.heading
                    Item {
                        anchors.fill: parent
                        transform: Scale {
                            origin.x: 24
                            origin.y: 24
                            xScale: stretchValue.value
                            yScale: 1 / stretchValue.value
                        }
                        Item {
                            id: figure
                            anchors.fill: parent
                            rotation: -root.heading

                            // The curl on top. It leans right at rest and springs up for a cheer.
                            Shape {
                                width: 48
                                height: 48
                                preferredRendererType: Shape.CurveRenderer
                                transform: Rotation {
                                    origin.x: 24
                                    origin.y: 3
                                    angle: root.state === "cheering" ? -18 : 0
                                    Behavior on angle { SpringAnimation { spring: 6; damping: 0.35 } }
                                }
                                ShapePath {
                                    fillColor: Theme.mascotEdge
                                    strokeColor: Theme.clear
                                    strokeWidth: -1
                                    PathSvg { path: "M20.5 4 C19 -2 23.5 -8.5 31 -9 C28 -6.5 27.2 -2.5 29.5 3 Z" }
                                }
                            }

                            // The body: a coral ball with a darker crescent of shade along its lower right
                            // (the part of the ball outside the same circle moved 3 left and 7 up).
                            Oval { cx: 24; cy: 24; rx: 24; ry: 24; fill: Theme.mascot }
                            Shape {
                                width: 48
                                height: 48
                                preferredRendererType: Shape.CurveRenderer
                                ShapePath {
                                    fillColor: Theme.mascotShade
                                    strokeColor: Theme.clear
                                    strokeWidth: -1
                                    PathSvg { path: "M0.72 29.84 A24 24 0 1 0 44.28 11.16 A24 24 0 0 1 0.72 29.84 Z" }
                                }
                            }

                            Repeater {
                                model: [11, 26]
                                delegate: Item {
                                    id: eye
                                    required property real modelData
                                    x: modelData
                                    y: 14
                                    width: 11
                                    height: 13

                                    // Open eyes: white, a pupil that looks, a tiny shine.
                                    Item {
                                        anchors.fill: parent
                                        visible: root.state !== "cheering"
                                        transform: Scale { id: lid; origin.y: 6.5; yScale: 1 }
                                        Oval { cx: 5.5; cy: 6.5; rx: 5.5; ry: 6.5; fill: Theme.text }
                                        Item {
                                            width: 6
                                            height: 6
                                            x: (eye.width - width) / 2 + root.gaze.x * root.reach
                                            y: (eye.height - height) / 2 + root.gaze.y * root.reach
                                            Behavior on x { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }
                                            Behavior on y { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }
                                            Oval { cx: 3; cy: 3; rx: 3; ry: 3; fill: Theme.onColour }
                                            Oval { cx: 4.3; cy: 1.9; rx: 0.9; ry: 0.9; fill: Theme.text }
                                        }
                                        SequentialAnimation {
                                            id: blink
                                            NumberAnimation { target: lid; property: "yScale"; to: 0.1; duration: 70; easing.type: Easing.InQuad }
                                            NumberAnimation { target: lid; property: "yScale"; to: 1; duration: 90; easing.type: Easing.OutQuad }
                                        }
                                        Connections {
                                            target: blinker
                                            function onTriggered() { blink.restart() }
                                        }
                                    }

                                    // Happy eyes for a cheer: two small arches.
                                    Shape {
                                        visible: root.state === "cheering"
                                        anchors.fill: parent
                                        preferredRendererType: Shape.CurveRenderer
                                        ShapePath {
                                            strokeColor: Theme.onColour
                                            strokeWidth: 2.4
                                            fillColor: Theme.clear
                                            capStyle: ShapePath.RoundCap
                                            PathSvg { path: "M1.5 8.5 C3 3.5 8 3.5 9.5 8.5" }
                                        }
                                    }
                                }
                            }

                            // The mouth: a smile, open for a cheer, small and sideways while thinking.
                            Shape {
                                width: 48
                                height: 48
                                preferredRendererType: Shape.CurveRenderer
                                ShapePath {
                                    strokeColor: root.state === "cheering" ? Theme.clear : Theme.onColour
                                    strokeWidth: root.state === "cheering" ? -1 : 2
                                    fillColor: root.state === "cheering" ? Theme.onColour : Theme.clear
                                    capStyle: ShapePath.RoundCap
                                    PathSvg {
                                        path: root.state === "cheering" ? "M19.5 30 C20.5 36 27.5 36 28.5 30 Z"
                                              : root.state === "thinking" ? "M21.5 32 C23 31.2 25 31.2 26.5 32.2"
                                              : "M20.5 30.5 C22 33.5 26 33.5 27.5 30.5"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Three dots beside the head while thinking, lit one after another.
        Rectangle {
            visible: root.state === "thinking"
            x: root.dotsLeft ? 4 - width : 44
            y: -10
            width: 26
            height: 12
            radius: 6
            color: Theme.surface2
            Row {
                anchors.centerIn: parent
                spacing: 2
                Repeater {
                    model: 3
                    delegate: Rectangle {
                        required property int index
                        width: 4
                        height: 4
                        radius: 2
                        color: Theme.text
                        opacity: dots.lit === index ? 1 : 0.35
                        Behavior on opacity { NumberAnimation { duration: Theme.durFast } }
                    }
                }
            }
            Timer {
                id: dots
                property int lit: 0
                interval: 300
                repeat: true
                running: root.state === "thinking" && root.visible
                onTriggered: lit = (lit + 1) % 3
            }
        }
    }

    // A stretch that eases in and springs back when the flight ends.
    QtObject {
        id: stretchValue
        property real value: root.stretch
        Behavior on value { NumberAnimation { duration: 180; easing.type: Easing.OutBack; easing.overshoot: 2 } }
    }

    // Blinks come every 4 to 6 seconds while resting or watching.
    Timer {
        id: blinker
        running: (root.state === "resting" || root.state === "watching") && root.visible
        repeat: true
        interval: 4000 + Math.random() * 2000
        onTriggered: interval = 4000 + Math.random() * 2000
    }
}
