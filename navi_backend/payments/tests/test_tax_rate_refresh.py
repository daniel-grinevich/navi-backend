from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.payments import taxjar
from navi_backend.payments.models import EffectiveTaxRate
from navi_backend.payments.tasks import refresh_effective_tax_rates


class TestFetchCombinedRate:
    @pytest.mark.django_db
    def test_parses_combined_rate(self):
        port = NaviPortFactory.build(
            postal_code="98101", state_or_region="WA", city="Seattle"
        )

        body = b'{"rate": {"combined_rate": "0.1025"}}'
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = body

        with mock.patch.object(taxjar.urllib.request, "urlopen", return_value=cm) as op:
            rate = taxjar.fetch_combined_rate(port)

            called_url = op.call_args.args[0].full_url
            assert "/rates/98101" in called_url
            assert "state=WA" in called_url

        assert rate == Decimal("0.1025")

    @pytest.mark.django_db
    def test_returns_none_without_postal_code(self):
        port = NaviPortFactory.build(postal_code="")
        with mock.patch.object(taxjar.urllib.request, "urlopen") as op:
            assert taxjar.fetch_combined_rate(port) is None
            op.assert_not_called()


@pytest.mark.django_db
class TestRefreshEffectiveTaxRates:
    def test_upserts_rate_per_port(self):
        port_a = NaviPortFactory(postal_code="98101")
        port_b = NaviPortFactory(postal_code="10001")

        rates = {port_a.pk: Decimal("0.1025"), port_b.pk: Decimal("0.08875")}
        with mock.patch(
            "navi_backend.payments.tasks.fetch_combined_rate",
            side_effect=lambda p: rates[p.pk],
        ):
            updated = refresh_effective_tax_rates()

        assert updated == 2
        assert EffectiveTaxRate.current_rate(port_a, timezone.localdate()) == Decimal(
            "0.1025"
        )

    def test_skips_ports_that_error_without_aborting(self):
        good = NaviPortFactory(postal_code="98101")
        bad = NaviPortFactory(postal_code="10001")

        def fake_fetch(port):
            if port.pk == bad.pk:
                raise RuntimeError
            return Decimal("0.10")

        with mock.patch(
            "navi_backend.payments.tasks.fetch_combined_rate", side_effect=fake_fetch
        ):
            updated = refresh_effective_tax_rates()

        # The failing port is skipped; the healthy one still updates.
        assert updated == 1
        assert EffectiveTaxRate.objects.filter(navi_port=good).exists()
        assert not EffectiveTaxRate.objects.filter(navi_port=bad).exists()
