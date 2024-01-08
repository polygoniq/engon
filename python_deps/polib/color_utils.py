# copyright (c) 2018- polygoniq xyz s.r.o.

# adapted code from http://www.easyrgb.com/en/math.php
import math
import numpy


def RGB_to_XYZ(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """Converts RGB coordinates to XYZ coordinates

    Expects RGB values between 0 and 1.
    Returns XYZ values between (0 to 0.9505, 0 to 1.0000, 0 to 1.0888).
    For use with Observer = 2°, Illuminant = D65.
    """
    gamma_neutral = [0.0, 0.0, 0.0]
    for i, color in enumerate(rgb):
        if color > 0.04045:
            color = ((color + 0.055) / 1.055) ** 2.4
        else:
            color = color / 12.92
        gamma_neutral[i] = color
    # Observer = 2°, Illuminant = D65
    x = gamma_neutral[0] * 0.4124 + gamma_neutral[1] * 0.3576 + gamma_neutral[2] * 0.1805
    y = gamma_neutral[0] * 0.2126 + gamma_neutral[1] * 0.7152 + gamma_neutral[2] * 0.0722
    z = gamma_neutral[0] * 0.0193 + gamma_neutral[1] * 0.1192 + gamma_neutral[2] * 0.9505
    return (x, y, z)


def XYZ_to_LAB(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    """Converts XYZ coordinates to CIELAB coordinates

    Expects XYZ values between (0 to 0.9505, 0 to 1.0000, 0 to 1.0888).
    Returns LAB values as (0 to 100, -128 to 128, -128 to 128).
    For use with Observer = 2°, Illuminant = D65.
    """
    X, Y, Z = xyz

    # Normalize the input values
    # Observer = 2°, Illuminant = D65
    var_X = X / 0.95047
    var_Y = Y
    var_Z = Z / 1.08883

    # Apply the transformation functions
    var_X = (var_X ** (1/3)) if var_X > 0.008856 else (7.787 * var_X + 16 / 116)
    var_Y = (var_Y ** (1/3)) if var_Y > 0.008856 else (7.787 * var_Y + 16 / 116)
    var_Z = (var_Z ** (1/3)) if var_Z > 0.008856 else (7.787 * var_Z + 16 / 116)

    CIE_L_star = (116 * var_Y) - 16
    CIE_a_star = 500 * (var_X - var_Y)
    CIE_b_star = 200 * (var_Y - var_Z)

    return (CIE_L_star, CIE_a_star, CIE_b_star)


def perceptual_color_distance(rgb_1: tuple[float, float, float],
                              rgb_2: tuple[float, float, float],
                              weight_luminosity: float = 1.0,
                              weight_chroma: float = 1.0,
                              weight_hue: float = 1.0) -> float:
    """Implements CIEDE2000 formula for perceptual color distance.

    Expects RGB values between 0 and 1.
    Returns a value between 0 and 1, where 0 represents identical color and 1 an opposite color.
    """
    lab_1 = XYZ_to_LAB(RGB_to_XYZ(rgb_1))
    lab_2 = XYZ_to_LAB(RGB_to_XYZ(rgb_2))

    # Implementation borrowed from: https://github.com/gtaylor/python-colormath

    lab_color_vector = numpy.array([lab_1[0], lab_1[1], lab_1[2]])
    L, a, b = lab_color_vector

    lab_color_matrix = numpy.array([(lab_2[0], lab_2[1], lab_2[2])])

    avg_Lp = (L + lab_color_matrix[:, 0]) / 2.0

    C1 = numpy.sqrt(numpy.sum(numpy.power(lab_color_vector[1:], 2)))
    C2 = numpy.sqrt(numpy.sum(numpy.power(lab_color_matrix[:, 1:], 2), axis=1))

    avg_C1_C2 = (C1 + C2) / 2.0

    G = 0.5 * (
        1
        - numpy.sqrt(
            numpy.power(avg_C1_C2, 7.0)
            / (numpy.power(avg_C1_C2, 7.0) + numpy.power(25.0, 7.0))
        )
    )

    a1p = (1.0 + G) * a
    a2p = (1.0 + G) * lab_color_matrix[:, 1]

    C1p = numpy.sqrt(numpy.power(a1p, 2) + numpy.power(b, 2))
    C2p = numpy.sqrt(numpy.power(a2p, 2) + numpy.power(lab_color_matrix[:, 2], 2))

    avg_C1p_C2p = (C1p + C2p) / 2.0

    h1p = numpy.degrees(numpy.arctan2(b, a1p))
    h1p += (h1p < 0) * 360

    h2p = numpy.degrees(numpy.arctan2(lab_color_matrix[:, 2], a2p))
    h2p += (h2p < 0) * 360

    avg_Hp = (((numpy.fabs(h1p - h2p) > 180) * 360) + h1p + h2p) / 2.0

    T = (
        1
        - 0.17 * numpy.cos(numpy.radians(avg_Hp - 30))
        + 0.24 * numpy.cos(numpy.radians(2 * avg_Hp))
        + 0.32 * numpy.cos(numpy.radians(3 * avg_Hp + 6))
        - 0.2 * numpy.cos(numpy.radians(4 * avg_Hp - 63))
    )

    diff_h2p_h1p = h2p - h1p
    delta_hp = diff_h2p_h1p + (numpy.fabs(diff_h2p_h1p) > 180) * 360
    delta_hp -= (h2p > h1p) * 720

    delta_Lp = lab_color_matrix[:, 0] - L
    delta_Cp = C2p - C1p
    delta_Hp = 2 * numpy.sqrt(C2p * C1p) * numpy.sin(numpy.radians(delta_hp) / 2.0)

    S_L = 1 + (
        (0.015 * numpy.power(avg_Lp - 50, 2))
        / numpy.sqrt(20 + numpy.power(avg_Lp - 50, 2.0))
    )
    S_C = 1 + 0.045 * avg_C1p_C2p
    S_H = 1 + 0.015 * avg_C1p_C2p * T

    delta_ro = 30 * numpy.exp(-(numpy.power(((avg_Hp - 275) / 25), 2.0)))
    R_C = numpy.sqrt(
        (numpy.power(avg_C1p_C2p, 7.0))
        / (numpy.power(avg_C1p_C2p, 7.0) + numpy.power(25.0, 7.0))
    )
    R_T = -2 * R_C * numpy.sin(2 * numpy.radians(delta_ro))

    distance = numpy.sqrt(
        numpy.power(delta_Lp / (S_L * weight_luminosity), 2)
        + numpy.power(delta_Cp / (S_C * weight_chroma), 2)
        + numpy.power(delta_Hp / (S_H * weight_hue), 2)
        + R_T * (delta_Cp / (S_C * weight_chroma)) * (delta_Hp / (S_H * weight_hue))
    )[0]

    # distance can be theoretically uncapped, but values above 100 are considered extremely different
    cap = 100
    if distance > cap:
        distance == cap

    return distance / cap
