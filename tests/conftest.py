"""
Shared fixtures for the QRE Backend test suite.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    """Provide a shared TestClient instance for the entire test session."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# QASM circuit fixtures
# ---------------------------------------------------------------------------

BELL_STATE_V2 = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2]; creg c[2];
h q[0]; cx q[0],q[1];
measure q -> c;
"""

GHZ_5Q_V2 = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[5]; creg c[5];
h q[0]; cx q[0],q[1]; cx q[1],q[2]; cx q[2],q[3]; cx q[3],q[4];
measure q -> c;
"""

QFT_4Q_V2 = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[4]; creg c[4];
h q[0]; cp(pi/2) q[1],q[0]; cp(pi/4) q[2],q[0]; cp(pi/8) q[3],q[0];
h q[1]; cp(pi/2) q[2],q[1]; cp(pi/4) q[3],q[1];
h q[2]; cp(pi/2) q[3],q[2];
h q[3];
swap q[0],q[3]; swap q[1],q[2];
measure q -> c;
"""

GROVER_3Q_V2 = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[3]; creg c[3];
h q[0]; h q[1]; h q[2];
x q[2]; h q[2]; ccx q[0],q[1],q[2]; h q[2]; x q[2];
h q[0]; h q[1]; h q[2];
x q[0]; x q[1]; x q[2];
h q[2]; ccx q[0],q[1],q[2]; h q[2];
x q[0]; x q[1]; x q[2];
h q[0]; h q[1]; h q[2];
measure q -> c;
"""

BERNSTEIN_VAZIRANI_V2 = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[5]; creg c[4];
x q[4];
h q[0]; h q[1]; h q[2]; h q[3]; h q[4];
cx q[0],q[4]; cx q[2],q[4]; cx q[3],q[4];
h q[0]; h q[1]; h q[2]; h q[3];
measure q[0]->c[0]; measure q[1]->c[1]; measure q[2]->c[2]; measure q[3]->c[3];
"""

TELEPORTATION_V2 = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[3]; creg c[2]; creg d[1];
h q[1]; cx q[1],q[2]; cx q[0],q[1]; h q[0];
measure q[0]->c[0]; measure q[1]->c[1];
if(c==1) z q[2];
if(c==2) x q[2];
if(c==3) y q[2];
measure q[2]->d[0];
"""

VQE_RY_CNOT_V2 = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[4]; creg c[4];
ry(0.3) q[0]; ry(0.7) q[1]; ry(1.2) q[2]; ry(0.5) q[3];
cx q[0],q[1]; cx q[1],q[2]; cx q[2],q[3];
ry(0.9) q[0]; ry(0.4) q[1]; ry(1.1) q[2]; ry(0.2) q[3];
measure q -> c;
"""

SINGLE_QUBIT_V2 = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[1]; creg c[1];
h q[0]; t q[0]; s q[0];
measure q -> c;
"""

BELL_STATE_V3 = """\
OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q; bit[2] c;
h q[0]; cx q[0],q[1];
c = measure q;
"""

TOFFOLI_3Q_V2 = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[3]; creg c[3];
x q[0]; x q[1];
ccx q[0],q[1],q[2];
measure q -> c;
"""

# Vendor names from vendors.json
AVAILABLE_VENDORS = {
    "Google Willow",
    "IBM Heron R3",
    "Rigetti Ankaa-3",
    "IonQ Tempo",
    "Quantinuum Helios",
    "Atom Computing",
    "QuEra Gemini",
}

UNAVAILABLE_VENDORS = {
    "PsiQuantum",
    "Xanadu",
    "Quandela",
}
