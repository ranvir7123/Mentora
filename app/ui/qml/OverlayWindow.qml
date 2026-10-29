import QtQuick
import QtQuick.Shapes
import QtQuick.Window
import Theme
import "mascot"

// The see-through layer over the whole screen: the ring around the real target and the flying mascot.
// It never takes a click or the keyboard; every click goes through to the app below.
//
// When the pointer appears, or the backend asks for "flying" again (Show me), the mascot leaves its spot
// in the panel, flies a curve, lands beside the target (never on it) and says a few words. After 3 s it
// flies home; the ring stays until the step passes, then turns mint and fades. When the target moves (the
// learner scrolled), the ring follows at once and the mascot lands again. A new pointer state interrupts
// whatever is moving. Positions from the bridge are logical pixels in screen coordinates.
Window {
    id: root
    required property var bridge
    readonly property var pointer: bridge.pointer

    readonly property real size: 48              // the mascot's body
    readonly property real headroom: 23          // kept free above it: the curl (9) and the cheering hop (14)
    readonly property real ringOutset: 4         // the ring sits this far outside the target
    readonly property real pulseReach: 4         // and its pulse swells this much further

    // The target in this window's coordinates.
    readonly property rect target: Qt.rect(bridge.pointerRect.x - x, bridge.pointerRect.y - y,
                                           bridge.pointerRect.width, bridge.pointerRect.height)

    x: Screen.virtualX
    y: Screen.virtualY
    width: Screen.width
    height: Screen.height
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
           | Qt.WindowDoesNotAcceptFocus | Qt.Tool
    visible: !warm || pointer.visible || flight.phase !== "home" || ring.opacity > 0
    color: Theme.clear
    // The layer's first appearance is slow (about 60 ms while its surface is made), which would stall the
    // mascot's first flight and the panel with it. So it is put on screen once at start, while it draws
    // nothing, and hides after that first frame.
    property bool warm: false
    onFrameSwapped: warm = true
    title: "Project X pointer"

    function toScreen(r) { return Qt.rect(r.x + root.x, r.y + root.y, r.width, r.height) }
    function fromScreen(p) { return Qt.point(p.x - root.x, p.y - root.y) }

    // What the mascot keeps clear of: the ring and its pulse, not only the target.
    function keepClear() {
        const t = bridge.pointerRect, d = ringOutset + pulseReach
        return Qt.rect(t.x - d, t.y - d, t.width + 2 * d, t.height + 2 * d)
    }
    function landing() { return fromScreen(bridge.landingSpot(keepClear(), size, headroom)) }
    function home() {
        const h = bridge.mascotHome
        return fromScreen(Qt.point(h.x + (h.width - size) / 2, h.y + (h.height - size) / 2))
    }

    // The flight: the mascot's top-left runs along a curve from `a` to `b`, bent by `c1` and `c2`, as `t`
    // goes from 0 to 1. phase: home (resting in the panel), out (flying to the target), landed, shift (a short
    // slide after the target moved a little), back (flying home).
    QtObject {
        id: flight
        property string phase: "home"
        property point a: Qt.point(0, 0)
        property point b: Qt.point(0, 0)
        property point c1: Qt.point(0, 0)
        property point c2: Qt.point(0, 0)
        property real t: 1
        readonly property real u: 1 - t
    }
    NumberAnimation {
        id: mover
        target: flight
        property: "t"
        from: 0
        to: 1
        easing.type: Easing.OutCubic
        onFinished: root.arrive()
    }

    function fly(from, to, how) {
        mover.stop()
        const d = Math.hypot(to.x - from.x, to.y - from.y)
        flight.a = from
        flight.b = to
        if (how === "shift") {              // a straight slide
            flight.c1 = Qt.point(from.x + (to.x - from.x) / 3, from.y + (to.y - from.y) / 3)
            flight.c2 = Qt.point(from.x + 2 * (to.x - from.x) / 3, from.y + 2 * (to.y - from.y) / 3)
        } else {                            // an arc that never crosses the target
            const bend = bridge.flightControl(Qt.point(from.x + x, from.y + y), Qt.point(to.x + x, to.y + y),
                                              size, headroom, keepClear())
            flight.c1 = fromScreen(bend[0])
            flight.c2 = fromScreen(bend[1])
        }
        flight.phase = how
        flight.t = 0
        mover.duration = how === "shift" ? Theme.durNormal : Math.round(400 + Math.min(100, d / 12))
        if (how !== "shift")
            words.said = false
        mover.start()
    }

    function goTo(spot, asked) {
        const here = Qt.point(mascot.x, mascot.y)
        const d = Math.hypot(spot.x - here.x, spot.y - here.y)
        if (flight.phase === "home") {
            bridge.mascotAway = true
            fly(home(), spot, "out")
        } else if ((flight.phase === "landed" || flight.phase === "shift") && d < 1) {
            if (asked) {                    // already there: say it again
                words.say()
                stay.restart()
            }
        } else if ((flight.phase === "landed" || flight.phase === "shift") && d < size && !asked) {
            fly(here, spot, "shift")
        } else {
            stay.stop()
            fly(here, spot, "out")
        }
    }

    function goHome() {
        stay.stop()
        if (flight.phase !== "home" && flight.phase !== "back")
            fly(Qt.point(mascot.x, mascot.y), home(), "back")
    }

    function arrive() {
        if (flight.phase === "out" || flight.phase === "shift")
            flight.phase = "landed"         // the mascot settles; it speaks once it has (onLanded)
        else if (flight.phase === "back") {
            flight.phase = "home"
            bridge.mascotAway = false
        }
    }

    // A new pointer state: work out what changed and move.
    property var last: ({ "visible": false, "x": 0, "y": 0, "w": 0, "h": 0, "mascot": "resting", "bubble": "" })
    function react() {
        const p = bridge.pointer, was = last
        last = { "visible": p.visible, "x": p.x, "y": p.y, "w": p.w, "h": p.h, "mascot": p.mascot, "bubble": p.bubble }
        ring.follow(p.visible ? p.ring : "none")
        if (!p.visible) {
            goHome()
            return
        }
        const moved = p.x !== was.x || p.y !== was.y || p.w !== was.w || p.h !== was.h
        const asked = p.mascot === "flying" && (!was.visible || was.mascot !== "flying" || moved)
        if (!was.visible || asked)
            goTo(landing(), true)
        else if (moved && flight.phase !== "home" && flight.phase !== "back")
            goTo(landing(), false)
        if (p.mascot === "cheering" && was.mascot !== "cheering" && flight.phase === "landed")
            stay.restart()                  // give the cheer its moment beside the target
        if (p.bubble !== was.bubble && flight.phase === "landed")
            words.say()
    }
    Connections {
        target: root.bridge
        function onPointerChanged() { root.react() }
    }
    Component.onCompleted: react()

    // After 3 s beside the target, home.
    Timer {
        id: stay
        interval: 3000
        onTriggered: root.goHome()
    }

    // The ring: a coral outline 4 px outside the target that pulses softly, mint for a moment when the step
    // passes, then gone.
    Item {
        id: ring
        x: root.target.x - root.ringOutset
        y: root.target.y - root.ringOutset
        width: root.target.width + 2 * root.ringOutset
        height: root.target.height + 2 * root.ringOutset
        property bool lit: false
        property bool mint: false
        opacity: lit ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.durNormal; easing.type: Easing.OutCubic } }

        function follow(mode) {
            if (mode === "pulse") {
                fade.stop()
                mint = false
                lit = true
            } else if (mode === "right") {
                mint = true
                lit = true
                fade.restart()
            } else {
                fade.stop()
                lit = false
            }
        }
        Timer { id: fade; interval: 350; onTriggered: ring.lit = false }

        Rectangle {
            anchors.fill: parent
            radius: Theme.radiusSmall
            color: Theme.clear
            border.width: 3
            border.color: Theme.accent
            opacity: ring.mint ? 0 : 1
            Behavior on opacity { NumberAnimation { duration: Theme.durFast } }
        }
        Rectangle {
            anchors.fill: parent
            radius: Theme.radiusSmall
            color: Theme.clear
            border.width: 3
            border.color: Theme.right
            opacity: ring.mint ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.durFast } }
        }
        // The pulse: a copy that swells by the same few pixels on every side and fades, now and then.
        Rectangle {
            id: pulse
            anchors.fill: parent
            radius: Theme.radiusSmall
            color: Theme.clear
            border.width: 3
            border.color: Theme.accent
            opacity: 0
            property real reach: 0
            transform: Scale {
                origin.x: pulse.width / 2
                origin.y: pulse.height / 2
                xScale: (pulse.width + 2 * pulse.reach) / Math.max(1, pulse.width)
                yScale: (pulse.height + 2 * pulse.reach) / Math.max(1, pulse.height)
            }
            SequentialAnimation {
                running: ring.lit && !ring.mint && root.visible
                loops: Animation.Infinite
                ParallelAnimation {
                    NumberAnimation { target: pulse; property: "reach"; from: 0; to: root.pulseReach; duration: 500; easing.type: Easing.OutCubic }
                    NumberAnimation { target: pulse; property: "opacity"; from: 0.6; to: 0; duration: 500; easing.type: Easing.OutCubic }
                }
                PauseAnimation { duration: 1100 }
                onRunningChanged: if (!running) pulse.opacity = 0
            }
        }
    }

    // The mascot's words: typed out a letter at a time, in a box beside it with a small tail toward it.
    Item {
        id: words
        readonly property string text: root.pointer.bubble !== "" ? root.pointer.bubble : "this one!"
        property bool said: false
        property int letters: 0
        readonly property bool shown: said && flight.phase === "landed" && root.pointer.visible
                                      && root.pointer.mascot !== "cheering" && root.pointer.ring !== "right"
        function say() {
            said = true
            letters = 0
            typing.restart()
        }

        width: Math.ceil(metrics.advanceWidth) + 2 * Theme.space12
        height: Math.ceil(metrics.height) + 2 * Theme.space8
        readonly property rect footprint: Qt.rect(mascot.x, mascot.y - root.headroom, root.size, root.size + root.headroom)
        readonly property point spot: root.fromScreen(root.bridge.bubbleSpot(root.keepClear(),
                                                      root.toScreen(footprint), width, height))
        x: spot.x
        y: spot.y
        opacity: shown ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }

        // Which edge the tail leaves from, and where along it: toward the mascot's middle.
        readonly property string side: y + height <= footprint.y ? "bottom" : y >= footprint.y + footprint.height ? "top"
                                       : x + width <= footprint.x ? "right" : "left"
        readonly property real along: side === "bottom" || side === "top"
                                      ? Math.max(Theme.radiusMedium + 4, Math.min(width - Theme.radiusMedium - 4, mascot.x + root.size / 2 - x))
                                      : Math.max(Theme.radiusMedium, Math.min(height - Theme.radiusMedium, mascot.y + root.size / 2 - y))

        TextMetrics {
            id: metrics
            font: label.font
            text: words.text
        }
        Rectangle {
            anchors.fill: parent
            radius: Theme.radiusMedium
            color: Theme.surface2
        }
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                fillColor: Theme.surface2
                strokeColor: Theme.clear
                strokeWidth: -1
                PathSvg {
                    readonly property real s: 7
                    readonly property real w: words.width
                    readonly property real h: words.height
                    readonly property real p: words.along
                    path: words.side === "bottom" ? `M ${p - s} ${h - 1} L ${p} ${h + s} L ${p + s} ${h - 1} Z`
                        : words.side === "top" ? `M ${p - s} 1 L ${p} ${-s} L ${p + s} 1 Z`
                        : words.side === "right" ? `M ${w - 1} ${p - s} L ${w + s} ${p} L ${w - 1} ${p + s} Z`
                        : `M 1 ${p - s} L ${-s} ${p} L 1 ${p + s} Z`
                }
            }
        }
        Text {
            id: label
            x: Theme.space12
            anchors.verticalCenter: parent.verticalCenter
            text: words.text.slice(0, words.letters)
            color: Theme.text
            font.family: Theme.fontBody
            font.weight: Font.ExtraBold
            font.pixelSize: Theme.size16
        }
        NumberAnimation {
            id: typing
            target: words
            property: "letters"
            from: 0
            to: words.text.length
            duration: 18 * words.text.length
        }
    }

    Mascot {
        id: mascot
        size: root.size
        visible: flight.phase !== "home"
        x: along(flight.a.x, flight.c1.x, flight.c2.x, flight.b.x)
        y: along(flight.a.y, flight.c1.y, flight.c2.y, flight.b.y)
        // The way it is going: the slope of the curve at this moment.
        heading: Math.atan2(slope(flight.a.y, flight.c1.y, flight.c2.y, flight.b.y),
                            slope(flight.a.x, flight.c1.x, flight.c2.x, flight.b.x)) * 180 / Math.PI
        function along(a, c1, c2, b) {
            const t = flight.t, u = flight.u
            return u * u * u * a + 3 * u * u * t * c1 + 3 * u * t * t * c2 + t * t * t * b
        }
        function slope(a, c1, c2, b) {
            const t = flight.t, u = flight.u
            return u * u * (c1 - a) + 2 * u * t * (c2 - c1) + t * t * (b - c2)
        }
        lookAt: Qt.point(root.target.x + root.target.width / 2, root.target.y + root.target.height / 2)
        dotsLeft: x + root.size / 2 < root.target.x + root.target.width / 2
        state: flight.phase === "out" || flight.phase === "back" ? "flying"
             : ["watching", "thinking", "cheering"].indexOf(root.pointer.mascot) >= 0 ? root.pointer.mascot : "watching"
        onLanded: if (flight.phase === "landed") {
            words.say()
            stay.restart()
        }
    }
}
