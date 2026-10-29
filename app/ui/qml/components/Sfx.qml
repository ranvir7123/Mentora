import QtQuick
import QtMultimedia

// The sound family: one short sound per cue (click, right, not_yet, complete, hop). Muted plays nothing;
// every sound has a visual twin on screen, so nothing is lost when it is off.
Item {
    id: root
    property bool muted: false

    function play(name) {
        if (muted)
            return
        const effect = ({ "click": click, "right": right, "not_yet": notYet, "complete": complete, "hop": hop })[name]
        if (effect)
            effect.play()
    }

    SoundEffect { id: click; source: Qt.resolvedUrl("../../sounds/click.wav"); volume: 0.5 }
    SoundEffect { id: right; source: Qt.resolvedUrl("../../sounds/right.wav"); volume: 0.6 }
    SoundEffect { id: notYet; source: Qt.resolvedUrl("../../sounds/not_yet.wav"); volume: 0.5 }
    SoundEffect { id: complete; source: Qt.resolvedUrl("../../sounds/complete.wav"); volume: 0.6 }
    SoundEffect { id: hop; source: Qt.resolvedUrl("../../sounds/hop.wav"); volume: 0.4 }
}
