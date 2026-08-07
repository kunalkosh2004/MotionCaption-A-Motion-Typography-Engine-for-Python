from motion_caption import Box, Point, Size
from motion_caption.models.geometry import Padding


class TestBox:
    def test_dimensions(self):
        box = Box(left=10, top=20, right=30, bottom=50)
        assert box.width == 20
        assert box.height == 30
        assert box.center_x == 20
        assert box.center_y == 35

    def test_from_point_size(self):
        box = Box.from_point_size(Point(x=1, y=2), Size(width=3, height=4))
        assert box.right == 4
        assert box.bottom == 6

    def test_contains(self):
        box = Box(0, 0, 10, 10)
        assert box.contains(Point(x=5, y=5))
        assert not box.contains(Point(x=11, y=5))

    def test_translate_and_scale(self):
        box = Box(0, 0, 10, 10).translate(5, 5)
        assert box == Box(5, 5, 15, 15)
        assert box.scale(2) == Box(10, 10, 30, 30)

    def test_union(self):
        a = Box(0, 0, 4, 4)
        b = Box(2, 2, 8, 6)
        assert a.union(b) == Box(0, 0, 8, 6)


class TestPadding:
    def test_uniform(self):
        p = Padding.uniform(16)
        assert (p.left.value, p.top.value, p.right.value, p.bottom.value) == (16, 16, 16, 16)

    def test_resolve(self, ctx):
        p = Padding(left=8, top="1em", right=4, bottom=2)
        sized = ctx.model_copy(update={"font_size": 50.0})
        box = p.resolve(sized)
        assert box.left == 8
        assert box.top == 50.0
        assert box.right == 4
        assert box.bottom == 2

    def test_is_zero(self):
        assert Padding().is_zero()
        assert not Padding(left=1).is_zero()
