import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

Future initFirebase() async {
  if (kIsWeb) {
    await Firebase.initializeApp(
        options: FirebaseOptions(
            apiKey: "AIzaSyCpMR-4Q-vsfQ7LmRDGfrMhe_3DfF0BThQ",
            authDomain: "vicoa-ivq0oy.firebaseapp.com",
            projectId: "vicoa-ivq0oy",
            storageBucket: "vicoa-ivq0oy.firebasestorage.app",
            messagingSenderId: "780704364741",
            appId: "1:780704364741:web:f0fc1b1a80f99e5d56d8ac"));
  } else {
    await Firebase.initializeApp();
  }
}
