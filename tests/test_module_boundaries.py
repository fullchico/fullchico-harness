"""A fronteira entre módulos é do harness, por lista branca: o projeto não escreve nem afrouxa a regra."""
import subprocess
import unittest

from tests.helpers import commit_all, make_repo, sync

CONF = 'VALIDATE_PUSH="true"\nMODULE_ROOTS="apps/api/src/modules"\nCONTRACT_PATHS="packages/contracts apps/api/src/shared"\n'


def write(repo, relative, text):
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class TestModuleBoundaries(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / "harness.conf").write_text(CONF)
        write(self.repo, "apps/api/src/modules/billing/domain/invoice.ts", "export type Invoice = {};\n")
        write(self.repo, "apps/api/src/shared/clock.ts", "export const now = () => new Date();\n")
        write(self.repo, "apps/api/src/config.ts", "export const config = {};\n")

    def validate(self):
        commit_all(self.repo, "chore: state")
        return subprocess.run([str(self.repo / ".harness/validate"), "--profile", "push"], cwd=self.repo, capture_output=True, text=True)

    def booking(self, source):
        write(self.repo, "apps/api/src/modules/booking/application/book.ts", source)

    def test_own_module_contract_and_packages_are_allowed(self):
        self.booking(
            'import { z } from "zod";\n'
            'import type { Slot } from "../domain/slot";\n'
            'import { now } from "../../../shared/clock";\n'
            'import { BookingDto } from "@acme/contracts";\n'
        )
        r = self.validate()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_another_module_is_reached_only_through_its_public_entry(self):
        write(self.repo, "apps/api/src/modules/billing/index.ts", "export {};\n")
        self.booking(
            'import { BillingModule } from "../../billing/index.js";\n'
            'import { BillingPort } from "../../billing";\n'
            'import { Guard } from "@/modules/billing";\n'
        )
        r = self.validate()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_the_inside_of_another_module_is_refused_in_every_form(self):
        for source in (
            'import { Invoice } from "../../billing/domain/invoice";\n',
            'import type { Invoice } from "../../billing/domain/invoice";\n',
            'export { Invoice } from "../../billing/domain/invoice";\n',
            'const invoice = require("../../billing/domain/invoice");\n',
            'const invoice = await import("../../billing/domain/invoice");\n',
            'import { Invoice } from "@/modules/billing/domain/invoice";\n',
            'import {\n  Invoice,\n} from "../../billing/domain/invoice";\n',
        ):
            with self.subTest(source=source):
                self.booking(source)
                r = self.validate()
                self.assertEqual(r.returncode, 1, source)
                self.assertIn("apps/api/src/modules/booking/application/book.ts:", r.stderr)
                self.assertIn("billing", r.stderr)

    def test_what_is_not_module_nor_contract_is_refused_too(self):
        self.booking('import { config } from "../../../config";\n')
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("CONTRACT_PATHS", r.stderr)

    def test_without_module_roots_nothing_is_checked(self):
        (self.repo / "harness.conf").write_text('VALIDATE_PUSH="true"\n')
        self.booking('import { Invoice } from "../../billing/domain/invoice";\n')
        self.assertEqual(self.validate().returncode, 0)
