"""
Serialization utilities for converting GameManager responses to JSON-ready format.

GameManager returns Python objects (Piece instances, tuples).
Flask needs JSON-serializable types (strings, lists, dicts).
"""


def coord_to_list(coord):
    """Convert tuple coordinate (x,y,z) to list [x,y,z]"""
    return list(coord)


def coord_to_string(coord):
    """Convert tuple coordinate to string key like '[0,0,0]'"""
    return str(list(coord))


def board_to_json(board_dict):
    """
    Convert board dict from:
        {(0,0,0): Pawn(white), (1,0,0): Rook(black), ...}
    To:
        {"[0,0,0]": "Pawn(white)", "[1,0,0]": "Rook(black)", ...}
    """
    json_board = {}
    for coord, piece in board_dict.items():
        # Convert tuple key to string key
        coord_key = coord_to_string(coord)
        # Convert piece object to string
        piece_str = str(piece)
        json_board[coord_key] = piece_str
    return json_board


def legal_moves_to_json(moves_list):
    """
    Convert list of tuple coordinates:
        [(0,1,0), (0,2,0), (1,1,0)]
    To:
        [[0,1,0], [0,2,0], [1,1,0]]
    """
    return [coord_to_list(coord) for coord in moves_list]


def move_history_to_json(move_history):
    """
    Convert move history list from:
        [{'from': (0,1,0), 'to': (0,2,0), 'moving_piece': 'Pawn(white)', ...}]
    To:
        [{'from': [0,1,0], 'to': [0,2,0], 'moving_piece': 'Pawn(white)', ...}]
    """
    json_history = []
    for move in move_history:
        json_move = move.copy()
        # Convert coordinate tuples to lists
        if 'from' in json_move and isinstance(json_move['from'], tuple):
            json_move['from'] = coord_to_list(json_move['from'])
        if 'to' in json_move and isinstance(json_move['to'], tuple):
            json_move['to'] = coord_to_list(json_move['to'])
        if 'via' in json_move and isinstance(json_move['via'], tuple):
            json_move['via'] = coord_to_list(json_move['via'])
        json_history.append(json_move)
    return json_history


def convert_response(response_dict):
    """
    Convert entire GameManager response to JSON-ready format.
    Handles board, legal_moves, move_history, and other coordinate-related fields.
    """
    # Make a copy to avoid modifying original
    json_response = response_dict.copy()

    # Convert board if present
    if "board" in json_response:
        json_response["board"] = board_to_json(json_response["board"])

    # Convert legal_moves if present
    if "legal_moves" in json_response:
        json_response["legal_moves"] = legal_moves_to_json(json_response["legal_moves"])

    # Convert move_history if present
    if "move_history" in json_response:
        json_response["move_history"] = move_history_to_json(json_response["move_history"])

    return json_response
