import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

MATPLOTLIB_AVAILABLE = True
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    MATPLOTLIB_AVAILABLE = False
    plt = None

if MATPLOTLIB_AVAILABLE:
    from slacwire.view import WireScanView


def _build_fake_data(detector="PMT29150"):
    profile_data = SimpleNamespace(
        positions=[0, 1, 2],
        detectors={detector: SimpleNamespace(values=[10, 20, 15])},
    )
    fit_data = SimpleNamespace(
        positions=[-1, 0, 1],
        curve=[12, 22, 14],
        mean=0.0,
        sigma=1.2,
        amplitude=20.0,
        offset=2.0,
    )
    return SimpleNamespace(
        collection_result=SimpleNamespace(raw_data={"WS28144": [0, 1, 2], detector: [5, 8, 6]}),
        profiles={"x": profile_data, "u": profile_data},
        fit_result={"x": SimpleNamespace(detectors={detector: fit_data}), "u": SimpleNamespace(detectors={detector: fit_data})},
    )


@unittest.skipUnless(MATPLOTLIB_AVAILABLE, "matplotlib not installed")
class TestWireScanView(unittest.TestCase):
    def test_draw_trajectory_populates_existing_figure(self):
        view = WireScanView()
        data = _build_fake_data()
        fig = plt.figure()

        view.draw_trajectory(fig, data, "WS28144", "PMT29150")

        self.assertEqual(len(fig.axes), 2)
        self.assertEqual(fig.axes[0].get_title(), "WS28144 Motion Trajectory")
        plt.close(fig)

    def test_draw_profile_tmitloss_uses_percent_label(self):
        view = WireScanView()
        data = _build_fake_data(detector="TMITLOSS")
        fig = plt.figure()

        view.draw_profile(fig, data, "WS28144", "TMITLOSS", "x")

        self.assertEqual(fig.axes[0].get_ylabel(), "% Beam Loss")
        plt.close(fig)

    def test_render_only_renders_profiles_present(self):
        view = WireScanView()
        data = _build_fake_data()

        fig_traj = MagicMock()
        fig_prof = MagicMock()
        view.plot_trajectory = MagicMock(return_value=fig_traj)
        view.plot_profile = MagicMock(return_value=fig_prof)
        view.save_fig = MagicMock(side_effect=[Path("traj.png"), Path("prof.png")])

        paths = view.render(
            data,
            wire="WS28144",
            detector="PMT29150",
            profiles=("x", "y"),
            file_prefix="OTF",
            plotdir=Path("."),
            stamp="20260423_123456",
            show=True,
            save=True,
        )

        view.plot_profile.assert_called_once_with(data, "x", "WS28144", "PMT29150")
        self.assertEqual(len(paths), 2)
        fig_traj.show.assert_called_once()


if __name__ == "__main__":
    unittest.main()
