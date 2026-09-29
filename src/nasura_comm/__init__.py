"""NASURA communication PoC (F-001).

Responsibilities:
    - Package root for the hub and car_ctrl processes and their pure logic
      modules (envelope, topics, filters, mapping, control, safety, signaling).

Non-responsibilities:
    - Browser-side code (lives under ``web/``).
    - Drive/Arm adapters downstream of the local UDP interface.
"""
