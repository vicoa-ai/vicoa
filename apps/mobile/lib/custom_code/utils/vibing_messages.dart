import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';

/// List of vibing messages to display while the agent is thinking
/// These are randomly selected to add personality to the loading state
const List<String> vibingMessages = [
  "Accomplishing",
  "Actioning",
  "Actualizing",
  "Architecting",
  "Baking",
  "Beaming",
  "Beboppin'",
  "Befuddling",
  "Billowing",
  "Blanching",
  "Bloviating",
  "Boogieing",
  "Boondoggling",
  "Booping",
  "Bootstrapping",
  "Brewing",
  "Bunning",
  "Burrowing",
  "Calculating",
  "Canoodling",
  "Caramelizing",
  "Cascading",
  "Catapulting",
  "Cerebrating",
  "Channeling",
  "Channelling",
  "Choreographing",
  "Churning",
  "Clauding",
  "Coalescing",
  "Cogitating",
  "Combobulating",
  "Composing",
  "Computing",
  "Concocting",
  "Considering",
  "Contemplating",
  "Cooking",
  "Crafting",
  "Creating",
  "Crunching",
  "Crystallizing",
  "Cultivating",
  "Deciphering",
  "Deliberating",
  "Determining",
  "Dilly-dallying",
  "Discombobulating",
  "Doing",
  "Doodling",
  "Drizzling",
  "Ebbing",
  "Effecting",
  "Elucidating",
  "Embellishing",
  "Enchanting",
  "Envisioning",
  "Evaporating",
  "Fermenting",
  "Fiddle-faddling",
  "Finagling",
  "Flambéing",
  "Flibbertigibbeting",
  "Flowing",
  "Flummoxing",
  "Fluttering",
  "Forging",
  "Forming",
  "Frolicking",
  "Frosting",
  "Gallivanting",
  "Galloping",
  "Garnishing",
  "Generating",
  "Gesticulating",
  "Germinating",
  "Gitifying",
  "Grooving",
  "Gusting",
  "Harmonizing",
  "Hashing",
  "Hatching",
  "Herding",
  "Honking",
  "Hullaballooing",
  "Hyperspacing",
  "Ideating",
  "Imagining",
  "Improvising",
  "Incubating",
  "Inferring",
  "Infusing",
  "Ionizing",
  "Jitterbugging",
  "Julienning",
  "Kneading",
  "Leavening",
  "Levitating",
  "Lollygagging",
  "Manifesting",
  "Marinating",
  "Meandering",
  "Metamorphosing",
  "Misting",
  "Moonwalking",
  "Moseying",
  "Mulling",
  "Mustering",
  "Musing",
  "Nebulizing",
  "Nesting",
  "Newspapering",
  "Noodling",
  "Nucleating",
  "Orbiting",
  "Orchestrating",
  "Osmosing",
  "Perambulating",
  "Percolating",
  "Perusing",
  "Philosophising",
  "Photosynthesizing",
  "Pollinating",
  "Pondering",
  "Pontificating",
  "Pouncing",
  "Precipitating",
  "Prestidigitating",
  "Processing",
  "Proofing",
  "Propagating",
  "Puttering",
  "Puzzling",
  "Quantumizing",
  "Razzle-dazzling",
  "Razzmatazzing",
  "Recombobulating",
  "Reticulating",
  "Roosting",
  "Ruminating",
  "Sautéing",
  "Scampering",
  "Schlepping",
  "Scurrying",
  "Seasoning",
  "Shenaniganing",
  "Shimmying",
  "Simmering",
  "Skedaddling",
  "Sketching",
  "Slithering",
  "Smooshing",
  "Sock-hopping",
  "Spelunking",
  "Spinning",
  "Sprouting",
  "Stewing",
  "Sublimating",
  "Swirling",
  "Swooping",
  "Symbioting",
  "Synthesizing",
  "Tempering",
  "Thinking",
  "Thundering",
  "Tinkering",
  "Tomfoolering",
  "Topsy-turvying",
  "Transfiguring",
  "Transmuting",
  "Twisting",
  "Undulating",
  "Unfurling",
  "Unravelling",
  "Vibing",
  "Waddling",
  "Wandering",
  "Warping",
  "Whatchamacalliting",
  "Whirlpooling",
  "Whirring",
  "Whisking",
  "Wibbling",
  "Working",
  "Wrangling",
  "Zesting",
  "Zigzagging",
];

/// Get a random vibing message with proper capitalization and ellipsis
String getRandomVibingMessage() {
  final random = Random();
  final message = vibingMessages[random.nextInt(vibingMessages.length)];
  // Capitalize first letter only and add ellipsis
  return '${message.substring(0, 1).toUpperCase()}${message.substring(1).toLowerCase()}…';
}

/// Get a random vibing message with a seed for reproducibility
/// This allows the same message to be shown for a given seed value
String getRandomVibingMessageWithSeed(int seed) {
  final random = Random(seed);
  final message = vibingMessages[random.nextInt(vibingMessages.length)];
  // Capitalize first letter only and add ellipsis
  return '${message.substring(0, 1).toUpperCase()}${message.substring(1).toLowerCase()}…';
}

/// Widget that displays a vibing message with animated wave effect
class VibingTextWidget extends StatefulWidget {
  final String message;
  final Color? textColor;
  final double? fontSize;

  const VibingTextWidget({
    Key? key,
    required this.message,
    this.textColor,
    this.fontSize,
  }) : super(key: key);

  @override
  State<VibingTextWidget> createState() => _VibingTextWidgetState();
}

class _VibingTextWidgetState extends State<VibingTextWidget> {
  static const int _baseCycleDurationMs = 6000;
  static const int _cycleDurationJitterMs = 6000;
  static const int _maxCyclePauseMs = 1500;
  static const int _tickIntervalMs = 50;

  late int _characterCount;
  late List<String> _characters;
  final _random = Random();
  double _progress = 0.0;
  Timer? _tickTimer;
  Timer? _cycleDelayTimer;
  late Duration _currentCycleDuration;
  DateTime? _cycleStartTime;

  @override
  void initState() {
    super.initState();
    _initializeCharacters();
    _startNewCycle();
  }

  @override
  void dispose() {
    _tickTimer?.cancel();
    _cycleDelayTimer?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant VibingTextWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.message != widget.message) {
      _initializeCharacters();
      _startNewCycle();
    }
  }

  void _initializeCharacters() {
    _characters = widget.message.split('');
    _characterCount = _characters.isEmpty ? 1 : _characters.length;
  }

  void _startNewCycle() {
    _cycleDelayTimer?.cancel();
    _cycleStartTime = DateTime.now();
    _currentCycleDuration = Duration(
      milliseconds:
          _baseCycleDurationMs + _random.nextInt(_cycleDurationJitterMs),
    );
    _progress = 0.0;
    _tickTimer?.cancel();
    _tickTimer = Timer.periodic(
      const Duration(milliseconds: _tickIntervalMs),
      (timer) {
        if (!mounted || _cycleStartTime == null) {
          timer.cancel();
          return;
        }

        final elapsed = DateTime.now().difference(_cycleStartTime!);
        final progress = elapsed.inMilliseconds /
            _currentCycleDuration.inMilliseconds;

        if (progress >= 1.0) {
          setState(() {
            _progress = 1.0;
          });
          timer.cancel();
          _scheduleNextCycle();
        } else {
          setState(() {
            _progress = progress;
          });
        }
      },
    );
  }

  void _scheduleNextCycle() {
    _cycleDelayTimer?.cancel();
    _cycleDelayTimer = Timer(
      Duration(
        milliseconds: 200 + _random.nextInt(_maxCyclePauseMs),
      ),
      () {
        if (!mounted) {
          return;
        }
        _startNewCycle();
      },
    );
  }

  double _calculateOpacity(int charIndex, double progress) {
    final normalizedIndex = charIndex / _characterCount;

    // Define spotlight width (how many characters are bright at once)
    const spotlightWidth = 0.2; // 20% of text length

    // Phase 1: Left to right (0.0 - 0.35)
    if (progress < 0.35) {
      final phaseProgress = progress / 0.35;
      final spotlightCenter = phaseProgress;
      final distance = (normalizedIndex - spotlightCenter).abs();

      if (distance < spotlightWidth / 2) {
        // Inside spotlight - bright
        return 0.9 - (distance / (spotlightWidth / 2)) * 0.4;
      }
      return 0.5; // Outside spotlight - dim
    }

    // Phase 2: Right to left (0.35 - 0.70)
    else if (progress < 0.70) {
      final phaseProgress = (progress - 0.35) / 0.35;
      final spotlightCenter = 1.0 - phaseProgress;
      final distance = (normalizedIndex - spotlightCenter).abs();

      if (distance < spotlightWidth / 2) {
        return 0.9 - (distance / (spotlightWidth / 2)) * 0.4;
      }
      return 0.5;
    }

    // Phase 3: Fast pass left to right (0.70 - 0.85)
    else if (progress < 0.85) {
      final phaseProgress = (progress - 0.70) / 0.15;
      final spotlightCenter = phaseProgress;
      final distance = (normalizedIndex - spotlightCenter).abs();

      if (distance < spotlightWidth / 3) { // Narrower spotlight for fast pass
        return 1.0 - (distance / (spotlightWidth / 3)) * 0.5;
      }
      return 0.5;
    }

    // Phase 4: Another fast pass (0.85 - 1.0)
    else {
      final phaseProgress = (progress - 0.85) / 0.15;
      final spotlightCenter = phaseProgress;
      final distance = (normalizedIndex - spotlightCenter).abs();

      if (distance < spotlightWidth / 3) {
        return 1.0 - (distance / (spotlightWidth / 3)) * 0.5;
      }
      return 0.5;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: _characters.asMap().entries.map((entry) {
        final index = entry.key;
        final char = entry.value;
        final opacity = _calculateOpacity(index, _progress);

        return Opacity(
          opacity: opacity.clamp(0.5, 1.0),
          child: Text(
            char,
            style: TextStyle(
              color: widget.textColor ?? Colors.grey,
              fontSize: widget.fontSize ?? 16.0,
            ),
          ),
        );
      }).toList(),
    );
  }
}
