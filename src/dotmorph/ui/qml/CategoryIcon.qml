import QtQuick
import QtQuick.Shapes

// Line icons drawn as vector paths (24x24 grid), so they tint with the theme.
Item {
    id: icon

    property string category: "image"
    property color color: "white"
    property real stroke: 1.8

    implicitWidth: 24
    implicitHeight: 24

    readonly property var paths: ({
        "image": "M3 5h18v14H3z M3 16l5-5 4 4 3-3 6 6 M15 8.5a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0 -3 0",
        "video": "M3 6h12v12H3z M15 10l6-3v10l-6-3z",
        "audio": "M9 18V5l11-2v13 M3 18a3 3 0 1 0 6 0a3 3 0 1 0 -6 0 M14 16a3 3 0 1 0 6 0a3 3 0 1 0 -6 0",
        "document": "M6 2h8l5 5v15H6z M14 2v5h5 M9 13h7 M9 17h7",
        "options": "M4 7h9 M17 7h3 M4 17h3 M11 17h9 M15 5v4 M9 15v4",
        "general": "M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6z M12 2v3 M12 19v3 M4.9 4.9l2.1 2.1 M17 17l2.1 2.1 M2 12h3 M19 12h3 M4.9 19.1L7 17 M17 7l2.1-2.1",
        "wheel": "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8z M12 3v5 M12 16v5 M3 12h5 M16 12h5",
        "keyboard": "M3 6h18v12H3z M7 10h.01 M11 10h.01 M15 10h.01 M7 14h10",
        "plug": "M9 2v6 M15 2v6 M6 8h12v4a6 6 0 0 1-12 0z M12 18v4",
        "folder": "M3 6h6l2 2h10v11H3z M9.5 13.5L12 11l2.5 2.5 M12 11v5",
        "wrench": "M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z",
        "info": "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z M12 11v6 M12 7.5v.5",
        "tools": "M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z M19 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"
    })

    Shape {
        width: 24
        height: 24
        scale: Math.min(icon.width, icon.height) / 24
        transformOrigin: Item.TopLeft
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: icon.color
            strokeWidth: icon.stroke
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: icon.paths[icon.category] || icon.paths["tools"] }
        }
    }
}
