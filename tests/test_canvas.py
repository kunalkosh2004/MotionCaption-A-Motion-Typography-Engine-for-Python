from motion_caption import AspectRatio, Canvas, StandardResolution


class TestStandardResolutions:
    def test_values(self):
        assert (
            Canvas.from_standard(StandardResolution.HD_1080P).width,
            Canvas.from_standard(StandardResolution.HD_1080P).height,
        ) == (1920, 1080)
        assert (
            Canvas.from_standard(StandardResolution.UHD_4K).width,
            Canvas.from_standard(StandardResolution.UHD_4K).height,
        ) == (3840, 2160)
        assert (
            Canvas.from_standard(StandardResolution.SQUARE).width,
            Canvas.from_standard(StandardResolution.SQUARE).height,
        ) == (1080, 1080)

    def test_string_coercion(self):
        assert (
            Canvas.from_standard("720p").width,
            Canvas.from_standard("720p").height,
        ) == (1280, 720)
        assert (
            Canvas.from_standard("2k").width,
            Canvas.from_standard("2k").height,
        ) == (2560, 1440)

    def test_shorts_is_portrait(self):
        canvas = Canvas.from_standard("shorts")
        assert canvas.is_portrait
        assert canvas.aspect_ratio is AspectRatio.PORTRAIT

    def test_square(self):
        canvas = Canvas.from_standard("square")
        assert canvas.is_square
        assert canvas.aspect_ratio is AspectRatio.SQUARE

    def test_landscape(self):
        canvas = Canvas.from_standard("1080p")
        assert canvas.is_landscape
        assert canvas.aspect_ratio is AspectRatio.LANDSCAPE


class TestCanvas:
    def test_custom(self):
        canvas = Canvas(width=800, height=600)
        assert canvas.aspect_ratio is AspectRatio.LANDSCAPE

    def test_invalid_dimensions(self):
        try:
            Canvas(width=0, height=100)
        except Exception:
            pass
        else:
            raise AssertionError("Canvas must reject non-positive dimensions")
