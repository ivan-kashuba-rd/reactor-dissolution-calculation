"""Salt dissolution in a stirred reactor - coursework calculation model.

This script reproduces the calculation logic from a supplied coursework
spreadsheet and makes the model easier to inspect, rerun and modify.

The calculation is theoretical. It is not a validated industrial reactor-design
or safety tool.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt


@dataclass
class ModelInputs:
    """Inputs for the stirred-reactor dissolution model.

    Units:
        delta_c_kg_m3: concentration driving force, kg/m^3
        salt_density_kg_m3: solid salt density, kg/m^3
        reactor_volume_m3: total reactor volume, m^3
        particle_diameter_m: characteristic particle diameter, m
        impeller_to_tank_diameter_ratio: D_impeller / D_tank, dimensionless
        tank_diameter_m: reactor diameter, m
        fill_fraction: liquid fill fraction, dimensionless
        liquid_density_kg_m3: solution density, kg/m^3
        diffusivity_m2_s: molecular diffusivity, m^2/s
        dynamic_viscosity_pa_s: dynamic viscosity, Pa*s
        power_number: impeller power coefficient, dimensionless
        motor_factor: multiplier from impeller power to motor power, dimensionless
        motor_limit_kw: available motor power, kW
    """

    delta_c_kg_m3: float = 44.0
    salt_density_kg_m3: float = 2265.0
    reactor_volume_m3: float = 63.0
    particle_diameter_m: float = 0.001
    impeller_to_tank_diameter_ratio: float = 0.40
    tank_diameter_m: float = 3.2
    fill_fraction: float = 0.80
    liquid_density_kg_m3: float = 1010.0
    diffusivity_m2_s: float = 2.2e-9
    dynamic_viscosity_pa_s: float = 0.00119
    power_number: float = 0.50
    motor_factor: float = 3.0
    motor_limit_kw: float = 5.0

    @property
    def impeller_diameter_m(self) -> float:
        return self.impeller_to_tank_diameter_ratio * self.tank_diameter_m


@dataclass
class ResultRow:
    rpm: float
    rps: float
    reynolds_number: float
    schmidt_number: float
    sherwood_number: float
    mass_transfer_coefficient_m_s: float
    dissolution_time_s: float
    calculated_mass_rate_kg_s: float
    impeller_power_w: float
    motor_power_w: float
    energy_j: float


def calculate_at_speed(rpm: float, inputs: ModelInputs) -> ResultRow:
    """Evaluate the coursework correlations at one impeller speed.

    Correlations implemented exactly as in the source spreadsheet:
        Re = n * d_m^2 * rho_l / mu
        Sc = mu / (rho_l * D)
        Sh = 0.8 * Re^0.5 * Sc^(1/3)
        k_c = Sh * D / d_p
        tau = rho_s * (d_p / 2) / (2 * k_c * DeltaC)
        G = V * phi * rho_l / tau
        N_impeller = K_m * rho_l * n^3 * d_m^5
        N_motor = motor_factor * N_impeller
        Q = N_motor * tau

    The model is valid only within the assumptions of the original coursework.
    """
    if rpm <= 0:
        raise ValueError("rpm must be positive")

    n_rps = rpm / 60.0
    d_impeller = inputs.impeller_diameter_m
    d_particle = inputs.particle_diameter_m

    reynolds = (
        n_rps
        * d_impeller**2
        * inputs.liquid_density_kg_m3
        / inputs.dynamic_viscosity_pa_s
    )
    schmidt = inputs.dynamic_viscosity_pa_s / (
        inputs.liquid_density_kg_m3 * inputs.diffusivity_m2_s
    )
    sherwood = 0.8 * reynolds**0.5 * schmidt ** (1.0 / 3.0)
    mass_transfer_coefficient = sherwood * inputs.diffusivity_m2_s / d_particle
    dissolution_time = (
        inputs.salt_density_kg_m3
        * (d_particle / 2.0)
        / (2.0 * mass_transfer_coefficient * inputs.delta_c_kg_m3)
    )
    calculated_mass_rate = (
        inputs.reactor_volume_m3
        * inputs.fill_fraction
        * inputs.liquid_density_kg_m3
        / dissolution_time
    )
    impeller_power = (
        inputs.power_number
        * inputs.liquid_density_kg_m3
        * n_rps**3
        * d_impeller**5
    )
    motor_power = impeller_power * inputs.motor_factor
    energy = motor_power * dissolution_time

    return ResultRow(
        rpm=rpm,
        rps=n_rps,
        reynolds_number=reynolds,
        schmidt_number=schmidt,
        sherwood_number=sherwood,
        mass_transfer_coefficient_m_s=mass_transfer_coefficient,
        dissolution_time_s=dissolution_time,
        calculated_mass_rate_kg_s=calculated_mass_rate,
        impeller_power_w=impeller_power,
        motor_power_w=motor_power,
        energy_j=energy,
    )


def inclusive_speed_range(min_rpm: float, max_rpm: float, step_rpm: float) -> Iterable[float]:
    if min_rpm <= 0 or max_rpm <= 0:
        raise ValueError("Speeds must be positive")
    if max_rpm < min_rpm:
        raise ValueError("max_rpm must be greater than or equal to min_rpm")
    if step_rpm <= 0:
        raise ValueError("step_rpm must be positive")

    count = int(math.floor((max_rpm - min_rpm) / step_rpm + 1e-12))
    for index in range(count + 1):
        yield round(min_rpm + index * step_rpm, 10)


def run_sweep(
    inputs: ModelInputs, min_rpm: float, max_rpm: float, step_rpm: float
) -> list[ResultRow]:
    return [
        calculate_at_speed(rpm, inputs)
        for rpm in inclusive_speed_range(min_rpm, max_rpm, step_rpm)
    ]


def select_maximum_speed_within_motor_limit(
    rows: list[ResultRow], motor_limit_kw: float
) -> ResultRow | None:
    """Return the fastest evaluated operating point within motor capacity.

    This is a capacity-screening rule, not a universal industrial optimisation.
    """
    limit_w = motor_limit_kw * 1000.0
    eligible = [row for row in rows if row.motor_power_w <= limit_w]
    return max(eligible, key=lambda row: row.rpm) if eligible else None


def write_csv(rows: list[ResultRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[field.name for field in fields(ResultRow)])
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def plot_results(rows: list[ResultRow], output_path: Path, recommended: ResultRow | None) -> None:
    rpm = [row.rpm for row in rows]
    time_s = [row.dissolution_time_s for row in rows]
    motor_power_kw = [row.motor_power_w / 1000.0 for row in rows]
    energy_j = [row.energy_j for row in rows]

    fig, axes = plt.subplots(3, 1, figsize=(8, 11), constrained_layout=True)

    axes[0].plot(rpm, time_s, marker="o", markersize=3)
    axes[0].set_title("Calculated dissolution time vs impeller speed")
    axes[0].set_xlabel("Impeller speed, rpm")
    axes[0].set_ylabel("Dissolution time, s")
    axes[0].grid(True)

    axes[1].plot(rpm, motor_power_kw, marker="o", markersize=3)
    axes[1].set_title("Calculated motor power vs impeller speed")
    axes[1].set_xlabel("Impeller speed, rpm")
    axes[1].set_ylabel("Motor power, kW")
    axes[1].grid(True)

    axes[2].plot(rpm, energy_j, marker="o", markersize=3)
    axes[2].set_title("Calculated energy per dissolution event vs impeller speed")
    axes[2].set_xlabel("Impeller speed, rpm")
    axes[2].set_ylabel("Energy, J")
    axes[2].grid(True)

    if recommended is not None:
        for axis in axes:
            axis.axvline(recommended.rpm, linestyle="--")
        axes[1].annotate(
            f"Highest tested speed within {recommended.motor_power_w / 1000:.2f} kW\nlimit: {recommended.rpm:.0f} rpm",
            xy=(recommended.rpm, recommended.motor_power_w / 1000.0),
            xytext=(8, -35),
            textcoords="offset points",
            arrowprops={"arrowstyle": "->"},
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def write_summary(
    inputs: ModelInputs,
    rows: list[ResultRow],
    recommended: ResultRow | None,
    output_path: Path,
) -> None:
    first_row = rows[0]
    last_row = rows[-1]
    lines = [
        "Salt dissolution in a stirred reactor - calculation summary",
        "=" * 58,
        f"Evaluated speed range: {first_row.rpm:g} to {last_row.rpm:g} rpm",
        f"Impeller diameter: {inputs.impeller_diameter_m:.3f} m",
        f"Motor capacity limit: {inputs.motor_limit_kw:.3f} kW",
        "",
        "Source-workbook check at the first speed:",
        f"  Re = {first_row.reynolds_number:.6f}",
        f"  Sc = {first_row.schmidt_number:.6f}",
        f"  Sh = {first_row.sherwood_number:.6f}",
        f"  k_c = {first_row.mass_transfer_coefficient_m_s:.12f} m/s",
        f"  tau = {first_row.dissolution_time_s:.12f} s",
        f"  motor power = {first_row.motor_power_w:.6f} W",
        "",
    ]
    if recommended:
        lines.extend(
            [
                "Simple capacity-screening recommendation:",
                f"  Highest evaluated speed within the motor limit: {recommended.rpm:g} rpm",
                f"  Calculated dissolution time: {recommended.dissolution_time_s:.4f} s",
                f"  Calculated motor power: {recommended.motor_power_w / 1000.0:.4f} kW",
                f"  Calculated energy: {recommended.energy_j:.2f} J",
            ]
        )
    else:
        lines.extend(
            [
                "No evaluated speed was within the motor-capacity limit.",
                "Review the speed range or increase the specified motor capacity.",
            ]
        )
    lines.extend(
        [
            "",
            "Important: This is a theoretical coursework model. It should not be used",
            "for real equipment sizing, safety decisions, or industrial process control",
            "without independent engineering validation and appropriate physical data.",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_inputs(config_path: Path | None) -> ModelInputs:
    if config_path is None:
        return ModelInputs()

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    allowed = {field.name for field in fields(ModelInputs)}
    unexpected = sorted(set(raw) - allowed)
    if unexpected:
        raise ValueError(f"Unknown input fields in config: {', '.join(unexpected)}")
    return ModelInputs(**raw)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate salt dissolution in a stirred reactor using coursework correlations."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional JSON file with model inputs. Defaults reproduce the coursework case.",
    )
    parser.add_argument("--min-rpm", type=float, default=10.0, help="Minimum impeller speed.")
    parser.add_argument("--max-rpm", type=float, default=100.0, help="Maximum impeller speed.")
    parser.add_argument("--step-rpm", type=float, default=1.0, help="Speed increment.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
        help="Folder where CSV, plot and summary files are written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inputs = load_inputs(args.config)
    rows = run_sweep(inputs, args.min_rpm, args.max_rpm, args.step_rpm)
    recommended = select_maximum_speed_within_motor_limit(rows, inputs.motor_limit_kw)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.output_dir / "dissolution_results.csv")
    plot_results(rows, args.output_dir / "dissolution_plots.png", recommended)
    write_summary(inputs, rows, recommended, args.output_dir / "summary.txt")

    if recommended is not None:
        print(
            "Highest evaluated speed within motor capacity: "
            f"{recommended.rpm:g} rpm "
            f"({recommended.motor_power_w / 1000.0:.3f} kW; "
            f"tau={recommended.dissolution_time_s:.3f} s)"
        )
    else:
        print("No evaluated speed was within the specified motor limit.")
    print(f"Results written to: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
